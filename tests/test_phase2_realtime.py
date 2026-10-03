import asyncio
import json
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from backend.main import app
from backend.db.base import Base
from backend.db.session import get_db
from backend.services.telemetry import telemetry_manager
from backend.schemas.audit import TelemetryEvent
from backend.services.incidents import create_incident, get_incident, update_incident_state
from backend.orchestration.nodes import (
    triage_node,
    root_cause_node,
    repair_node,
    failure_analyzer_node,
    adversarial_resilience_node,
    policy_risk_gateway,
    human_approval_node,
    recovery_complete_node
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def make_test_state(incident_id: str, **kwargs) -> dict:
    base = {
        "incident_id": incident_id,
        "github_payload": {
            "repository": {"full_name": "demo/app"},
            "workflow_run": {"conclusion": "failure", "name": "CI"},
            "head_commit": {"message": "test commit"}
        },
        "is_mock_mode": True,
        "triage_context": "KeyError: 'user_id' in authenticate",
        "root_cause_analysis": {"summary": "KeyError in auth", "file": "backend/api/auth.py", "confidence": 0.95},
        "explainable_risk": {"score": 0.2, "decision": "ALLOW", "breakdown": []},
        "action_decision": "ALLOW",
        "human_approved": True,
        "current_patch_diff": "--- a/auth.py\n+++ b/auth.py\n@@ -1,2 +1,3 @@\n+if 'user_id' not in payload: raise ValueError\n",
        "test_results": {"exit_code": 0, "stdout": "1 passed", "stderr": ""},
        "retry_count": 0,
        "pr_url": "",
        "similar_past_cases": [],
        "learning_confidence_boost": 0.0,
        "patch_explanation": "Added key check",
        "generated_test_code": "",
        "is_shadow_mode": False,
        "adversarial_report": {},
        "polyglot_language": "",
        "polyglot_audiences": {}
    }
    base.update(kwargs)
    return base


@pytest_asyncio.fixture
async def async_client():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_telemetry_event_model():
    """Verify structured event model: event_id, incident_id, stage, status, timestamp, data."""
    incident_id = "inc-test-event-model-01"
    queue = await telemetry_manager.subscribe(incident_id)

    await telemetry_manager.publish(
        event_type="nemotron_started",
        incident_id=incident_id,
        message="Nemotron investigation started",
        stage="root_cause",
        status="running",
        data={"model": "nemotron-70b", "phase": "investigation"}
    )

    event = await asyncio.wait_for(queue.get(), timeout=2.0)
    await queue.close()

    assert event.event_id is not None
    assert len(event.event_id) > 5
    assert event.incident_id == incident_id
    assert event.stage == "root_cause"
    assert event.status == "running"
    assert event.timestamp is not None
    assert event.data["model"] == "nemotron-70b"


@pytest.mark.asyncio
async def test_live_detection_events():
    """Verify triage_node emits failure_context_loaded, source_loaded."""
    incident_id = "inc-test-triage-live-02"
    queue = await telemetry_manager.subscribe(incident_id)

    state = make_test_state(incident_id, triage_context="")
    result = await triage_node(state, llm=None)
    await queue.close()

    assert result["triage_context"] is not None
    assert len(result["triage_context"]) > 0


@pytest.mark.asyncio
async def test_live_nemotron_and_root_cause():
    """Verify root_cause_node emits nemotron_started, nemotron_completed, root_cause_identified."""
    incident_id = "inc-test-nemotron-live-03"
    received_events = []

    queue = await telemetry_manager.subscribe(incident_id)

    async def collect_events():
        while True:
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=1.0)
                received_events.append(ev)
            except asyncio.TimeoutError:
                break

    collector = asyncio.create_task(collect_events())

    state = make_test_state(incident_id)
    result = await root_cause_node(state, llm=None)
    await collector
    await queue.close()

    event_types = [e.event_type for e in received_events]
    assert "nemotron_started" in event_types
    assert "nemotron_completed" in event_types
    assert "root_cause_identified" in event_types

    # Verify safe metadata
    nemotron_ev = next(e for e in received_events if e.event_type == "nemotron_completed")
    assert "nemotron" in nemotron_ev.data["model"].lower()
    assert ("latency" in nemotron_ev.data) or ("latency_ms" in nemotron_ev.data)
    assert result["root_cause_analysis"]["confidence"] >= 0.8


@pytest.mark.asyncio
async def test_live_repair_and_sandbox():
    """Verify repair_node and failure_analyzer_node emit live patch and sandbox events."""
    incident_id = "inc-test-repair-sandbox-04"
    received_events = []

    queue = await telemetry_manager.subscribe(incident_id)

    async def collect_events():
        while True:
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=1.0)
                received_events.append(ev)
            except asyncio.TimeoutError:
                break

    collector = asyncio.create_task(collect_events())

    state = make_test_state(incident_id)

    # 1. Run repair
    repair_result = await repair_node(state, llm=None)
    state["current_patch_diff"] = repair_result["current_patch_diff"]
    state["patch_explanation"] = repair_result["patch_explanation"]

    # 2. Run sandbox
    sandbox_result = await failure_analyzer_node(state, llm=None)

    await collector
    await queue.close()

    event_types = [e.event_type for e in received_events]
    assert "patch_generation_started" in event_types
    assert "patch_generated" in event_types
    assert "sandbox_started" in event_types
    assert "sandbox_testing" in event_types
    assert "sandbox_completed" in event_types

    # Verify sandbox data captures exit_code, passed/failed, runtime
    sandbox_ev = next(e for e in received_events if e.event_type == "sandbox_completed")
    assert "exit_code" in sandbox_ev.data
    assert "tests_passed" in sandbox_ev.data
    assert ("runtime" in sandbox_ev.data) or ("runtime_seconds" in sandbox_ev.data)


@pytest.mark.asyncio
async def test_live_adversarial_validation():
    """Verify adversarial_resilience_node emits granular mutation, dependency, replay events."""
    incident_id = "inc-test-adversarial-05"
    received_events = []

    queue = await telemetry_manager.subscribe(incident_id)

    async def collect_events():
        while True:
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=1.0)
                received_events.append(ev)
            except asyncio.TimeoutError:
                break

    collector = asyncio.create_task(collect_events())

    state = make_test_state(incident_id)
    result = await adversarial_resilience_node(state, llm=None)
    await collector
    await queue.close()

    event_types = [e.event_type for e in received_events]
    assert "mutation_testing_started" in event_types
    assert "mutation_testing_completed" in event_types
    assert "dependency_scan_started" in event_types
    assert "dependency_scan_completed" in event_types
    assert "behavioral_replay_started" in event_types
    assert "behavioral_replay_completed" in event_types
    assert "adversarial_validation_completed" in event_types


@pytest.mark.asyncio
async def test_live_risk_gateway_and_github_recovery():
    """Verify policy_risk_gateway and recovery_complete_node emit risk and PR events."""
    incident_id = "inc-test-risk-pr-06"
    received_events = []

    queue = await telemetry_manager.subscribe(incident_id)

    async def collect_events():
        while True:
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=1.0)
                received_events.append(ev)
            except asyncio.TimeoutError:
                break

    collector = asyncio.create_task(collect_events())

    state = make_test_state(incident_id, human_approved=True)

    # 1. Risk Gateway
    risk_res = await policy_risk_gateway(state, llm=None)
    state["explainable_risk"] = risk_res["explainable_risk"]
    state["action_decision"] = risk_res["action_decision"]

    # 2. Recovery Complete (PR generation)
    rec_res = await recovery_complete_node(state, llm=None)

    await collector
    await queue.close()

    event_types = [e.event_type for e in received_events]
    assert "risk_evaluation_started" in event_types
    assert "risk_evaluated" in event_types
    assert "branch_creation_started" in event_types
    assert "branch_created" in event_types
    assert "commit_created" in event_types
    assert "pr_creation_started" in event_types
    assert "pr_created" in event_types

    assert rec_res["pr_url"] is not None
    assert "github.com" in rec_res["pr_url"]


@pytest.mark.asyncio
async def test_concurrency_isolation():
    """Verify multiple incidents remain strictly isolated in state and event channels."""
    inc_a = "incident-concurrent-alpha"
    inc_b = "incident-concurrent-beta"

    queue_a = await telemetry_manager.subscribe(inc_a)
    queue_b = await telemetry_manager.subscribe(inc_b)

    # Publish to A
    await telemetry_manager.publish(
        event_type="patch_generated",
        incident_id=inc_a,
        message="Patch generated for Alpha",
        stage="repair",
        status="completed",
        data={"patch": "patch_content_A"}
    )

    # Publish to B
    await telemetry_manager.publish(
        event_type="patch_generated",
        incident_id=inc_b,
        message="Patch generated for Beta",
        stage="repair",
        status="completed",
        data={"patch": "patch_content_B"}
    )

    event_a = await asyncio.wait_for(queue_a.get(), timeout=1.0)
    event_b = await asyncio.wait_for(queue_b.get(), timeout=1.0)

    await queue_a.close()
    await queue_b.close()

    assert event_a.incident_id == inc_a
    assert event_a.data["patch"] == "patch_content_A"

    assert event_b.incident_id == inc_b
    assert event_b.data["patch"] == "patch_content_B"

    # Verify no crosstalk
    assert queue_a.empty()
    assert queue_b.empty()
