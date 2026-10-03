from __future__ import annotations

import asyncio
import copy
import json
import hmac
import hashlib
import os
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from backend.main import app
from backend.db.base import Base
from backend.db.session import get_db
from backend.orchestration.state import RecoveryState


REQUIRED_STATE_KEYS: tuple[str, ...] = (
    "incident_id",
    "github_payload",
    "is_mock_mode",
    "triage_context",
    "root_cause_analysis",
    "explainable_risk",
    "action_decision",
    "human_approved",
    "current_patch_diff",
    "test_results",
    "retry_count",
    "pr_url",
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def e2e_client():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


def assert_recovery_state_contract(
    state: dict[str, Any],
) -> None:
    assert set(REQUIRED_STATE_KEYS).issubset(
        state.keys()
    ), (
        "RecoveryState lost required keys: "
        f"{set(REQUIRED_STATE_KEYS) - set(state.keys())}"
    )

    assert isinstance(state["incident_id"], str)
    assert isinstance(state["github_payload"], dict)
    assert isinstance(state["is_mock_mode"], bool)
    assert isinstance(state["triage_context"], str)
    assert isinstance(state["root_cause_analysis"], dict)

    risk = state["explainable_risk"]

    assert isinstance(risk, dict)
    assert "score" in risk
    assert "breakdown" in risk
    assert "decision" in risk

    assert isinstance(
        risk["score"],
        (int, float),
    )
    assert isinstance(
        risk["breakdown"],
        list,
    )
    assert risk["decision"] in {
        "ALLOW",
        "APPROVE",
        "BLOCK",
    }

    assert state["action_decision"] in {
        "ALLOW",
        "APPROVE",
        "BLOCK",
    }

    assert isinstance(
        state["human_approved"],
        bool,
    )

    assert isinstance(
        state["current_patch_diff"],
        str,
    )

    test_results = state["test_results"]

    assert isinstance(
        test_results,
        dict,
    )
    assert {
        "stdout",
        "stderr",
        "exit_code",
    }.issubset(test_results.keys())

    assert isinstance(
        test_results["stdout"],
        str,
    )
    assert isinstance(
        test_results["stderr"],
        str,
    )
    assert isinstance(
        test_results["exit_code"],
        int,
    )

    assert isinstance(
        state["retry_count"],
        int,
    )

    assert isinstance(
        state["pr_url"],
        str,
    )


def build_demo_payload() -> dict[str, Any]:
    return {
        "action": "completed",
        "workflow_run": {
            "id": 987654321,
            "name": "pytest",
            "conclusion": "failure",
            "head_branch": "main",
            "head_sha": "0123456789abcdef",
            "repository": {
                "full_name": "demo/autonomous-recovery-engine",
            },
        },
        "repository": {
            "full_name": "demo/autonomous-recovery-engine",
        },
        "sender": {
            "login": "github-actions",
        },
    }

from backend.config import get_settings

def sign_payload(payload_bytes: bytes, secret: str = None) -> str:
    secret = secret or get_settings().github_webhook_secret
    digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.mark.asyncio
async def test_webhook_ingress_to_recovery_lifecycle(
    e2e_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.config import get_settings
    monkeypatch.setattr(get_settings(), "allow_mock_mode", True)
    from backend.orchestration.runtime import recovery_runtime

    payload = build_demo_payload()

    initial_state: RecoveryState = {
        "incident_id": "integration-test-incident",
        "github_payload": payload,
        "is_mock_mode": True,
        "triage_context": "",
        "root_cause_analysis": {},
        "explainable_risk": {
            "score": 0.0,
            "breakdown": [],
            "decision": "ALLOW",
        },
        "action_decision": "ALLOW",
        "human_approved": False,
        "current_patch_diff": "",
        "test_results": {
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
        },
        "retry_count": 0,
        "pr_url": "",
    }

    states: list[dict[str, Any]] = []

    async def fake_run(
        state: RecoveryState,
    ) -> dict[str, Any]:
        current = copy.deepcopy(state)
        states.append(copy.deepcopy(current))
        assert_recovery_state_contract(current)

        current["triage_context"] = (
            "Mock triage identified the target authentication "
            "validation regression."
        )

        states.append(copy.deepcopy(current))
        assert_recovery_state_contract(current)

        current["root_cause_analysis"] = {
            "error": "KeyError: 'user_id'",
            "file": "backend/api/auth.py",
            "root_cause": (
                "Authentication handler directly indexes user_id "
                "without validating the request payload."
            ),
        }

        states.append(copy.deepcopy(current))
        assert_recovery_state_contract(current)

        current["explainable_risk"] = {
            "score": 0.41,
            "breakdown": [
                {
                    "factor": "critical_file",
                    "value": 0.60,
                    "weight": 0.50,
                    "contribution": 0.30,
                    "explanation": (
                        "Authentication code is security-sensitive."
                    ),
                },
                {
                    "factor": "patch_scope",
                    "value": 0.20,
                    "weight": 0.30,
                    "contribution": 0.06,
                    "explanation": (
                        "Patch modifies one application file."
                    ),
                },
                {
                    "factor": "test_coverage",
                    "value": 0.10,
                    "weight": 0.40,
                    "contribution": 0.04,
                    "explanation": (
                        "Regression test covers the missing payload."
                    ),
                },
            ],
            "decision": "APPROVE",
        }

        current["action_decision"] = "APPROVE"

        states.append(copy.deepcopy(current))
        assert_recovery_state_contract(current)

        current["current_patch_diff"] = (
            "--- a/backend/api/auth.py\n"
            "+++ b/backend/api/auth.py\n"
            "@@ -1,5 +1,10 @@\n"
            "+    user_id = payload.get('user_id')\n"
            "+    if not user_id:\n"
            "+        raise ValueError('user_id is required')\n"
        )

        states.append(copy.deepcopy(current))
        assert_recovery_state_contract(current)

        current["test_results"] = {
            "stdout": (
                "3 passed in 0.31s\n"
                "authentication payload validation verified\n"
            ),
            "stderr": "",
            "exit_code": 0,
        }

        states.append(copy.deepcopy(current))
        assert_recovery_state_contract(current)

        return current

    async def fake_get_state(
        incident_id: str,
    ) -> dict[str, Any]:
        if states:
            return copy.deepcopy(states[-1])
        return copy.deepcopy(initial_state)

    async def fake_resume(
        incident_id: str,
        approved: bool,
    ) -> None:
        assert approved is True

        current = copy.deepcopy(states[-1])
        current["human_approved"] = True

        current["pr_url"] = (
            "https://github.com/demo/"
            "autonomous-recovery-engine/pull/42"
        )

        states.append(current)
        assert_recovery_state_contract(current)

    monkeypatch.setattr(
        recovery_runtime,
        "run",
        fake_run,
    )

    monkeypatch.setattr(
        recovery_runtime,
        "get_state",
        fake_get_state,
    )

    monkeypatch.setattr(
        recovery_runtime,
        "resume",
        fake_resume,
    )

    webhook_url = "/webhook/github"
    body_bytes = json.dumps(payload).encode("utf-8")

    webhook_response = await e2e_client.post(
        webhook_url,
        content=body_bytes,
        headers={
            "X-GitHub-Event": "workflow_run",
            "X-GitHub-Delivery": "integration-test-delivery",
            "X-Recovery-Mock": "true",
            "X-Hub-Signature-256": sign_payload(body_bytes)
        },
    )

    assert webhook_response.status_code in {200, 202}
    webhook_body = webhook_response.json()
    assert webhook_body["accepted"] is True
    assert webhook_body["is_mock_mode"] is True

    incident_id = webhook_body["incident_id"]
    assert incident_id

    await recovery_runtime.run(
        {
            **initial_state,
            "incident_id": incident_id,
        }
    )

    latest_state = states[-1]
    assert_recovery_state_contract(latest_state)
    assert latest_state["current_patch_diff"]
    assert latest_state["test_results"]["exit_code"] == 0
    assert latest_state["action_decision"] == "APPROVE"

    states[-1]["incident_id"] = incident_id

    approval_response = await e2e_client.post(
        f"/api/v1/incident/{incident_id}/approve",
        json={
            "approved": True,
            "operator": "integration-test",
        },
    )

    assert approval_response.status_code == 200
    approval_body = approval_response.json()
    assert approval_body["approved"] is True
    assert approval_body["resumed"] is True
    assert approval_body["next_node"] == "pr_creator_node"

    final_state = states[-1]
    assert_recovery_state_contract(final_state)
    assert final_state["human_approved"] is True
    assert final_state["pr_url"].startswith("https://github.com/")


@pytest.mark.asyncio
async def test_approval_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.api.approval_handler import ApprovalLifecycle

    lifecycle = ApprovalLifecycle()

    state: RecoveryState = {
        "incident_id": "idempotency-test",
        "github_payload": {},
        "is_mock_mode": True,
        "triage_context": "ready",
        "root_cause_analysis": {
            "error": "KeyError: 'user_id'",
        },
        "explainable_risk": {
            "score": 0.35,
            "breakdown": [],
            "decision": "APPROVE",
        },
        "action_decision": "APPROVE",
        "human_approved": False,
        "current_patch_diff": "diff --git a/backend/api/auth.py",
        "test_results": {
            "stdout": "1 passed",
            "stderr": "",
            "exit_code": 0,
        },
        "retry_count": 0,
        "pr_url": "",
    }

    from backend.orchestration.runtime import recovery_runtime

    resume_count = 0

    async def fake_get_state(incident_id: str) -> dict[str, Any]:
        return copy.deepcopy(state)

    async def fake_resume(incident_id: str, approved: bool) -> None:
        nonlocal resume_count
        resume_count += 1
        assert incident_id == state["incident_id"]
        assert approved is True

    monkeypatch.setattr(recovery_runtime, "get_state", fake_get_state)
    monkeypatch.setattr(recovery_runtime, "resume", fake_resume)

    from backend.api.approval_handler import ApprovalRequest

    request = ApprovalRequest(
        approved=True,
        operator="test",
    )

    first = await lifecycle.approve(
        incident_id=state["incident_id"],
        request=request,
    )

    second = await lifecycle.approve(
        incident_id=state["incident_id"],
        request=request,
    )

    assert first.resumed is True
    assert first.idempotent is False

    assert second.resumed is False
    assert second.idempotent is True

    assert resume_count == 1


@pytest.mark.asyncio
async def test_state_contract_survives_every_required_transition() -> None:
    state: RecoveryState = {
        "incident_id": "contract-test",
        "github_payload": build_demo_payload(),
        "is_mock_mode": True,
        "triage_context": "",
        "root_cause_analysis": {},
        "explainable_risk": {
            "score": 0.0,
            "breakdown": [],
            "decision": "ALLOW",
        },
        "action_decision": "ALLOW",
        "human_approved": False,
        "current_patch_diff": "",
        "test_results": {
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
        },
        "retry_count": 0,
        "pr_url": "",
    }

    assert_recovery_state_contract(state)

    transitions = [
        {"triage_context": "triaged"},
        {"root_cause_analysis": {"exception": "KeyError: 'user_id'"}},
        {
            "explainable_risk": {
                "score": 0.4,
                "breakdown": [],
                "decision": "APPROVE",
            },
            "action_decision": "APPROVE",
        },
        {"current_patch_diff": "diff --git a/backend/api/auth.py"},
        {
            "test_results": {
                "stdout": "3 passed",
                "stderr": "",
                "exit_code": 0,
            },
        },
        {"human_approved": True},
        {"pr_url": "https://github.com/demo/repo/pull/1"},
    ]

    for mutation in transitions:
        state.update(mutation)
        assert_recovery_state_contract(state)

    assert state["retry_count"] == 0
    assert state["human_approved"] is True
    assert state["test_results"]["exit_code"] == 0
    assert state["pr_url"].endswith("/pull/1")
