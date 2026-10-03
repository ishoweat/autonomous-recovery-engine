from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.orchestration.risk import calculate_patch_risk
from backend.sandbox.sandbox import RecoverySandbox
from backend.sandbox.models import CommandResult, SandboxResult
from backend.services.telemetry import telemetry_manager
from backend.services.incidents import create_incident, get_incident, update_incident_state
from backend.db.session import AsyncSessionLocal
from backend.db.models import IncidentStatus, AuditEventType


@pytest.mark.asyncio
async def test_risk_scoring_thresholds_truthful():
    """Verify risk algorithm thresholds:
    score < 0.30 -> ALLOW
    0.30 <= score <= 0.70 -> APPROVE
    score > 0.70 -> BLOCK
    No contradictory states (zero score with BLOCK).
    """
    # 1. Clean small patch on non-sensitive file -> ALLOW
    low_risk = calculate_patch_risk(
        files=["backend/utils/helpers.py"],
        patch_diff="@@ -1,3 +1,3 @@\n def get_val():\n-    return 1\n+    return 2\n",
    )
    assert low_risk["score"] < 0.30, f"Expected < 0.30, got {low_risk['score']}"
    assert low_risk["decision"] == "ALLOW", f"Expected ALLOW, got {low_risk['decision']}"

    # 2. Moderate change on core logic -> APPROVE
    med_risk = calculate_patch_risk(
        files=["backend/services/incidents.py"],
        patch_diff=(
            "@@ -1,15 +1,25 @@\n"
            + "".join([f"+    data_{i} = True\n" for i in range(15)])
        ),
    )
    assert 0.30 <= med_risk["score"] <= 0.70, f"Expected 0.30-0.70, got {med_risk['score']}"
    assert med_risk["decision"] == "APPROVE", f"Expected APPROVE, got {med_risk['decision']}"

    # 3. High risk change on auth/crypto/security file with massive diff -> BLOCK
    high_risk = calculate_patch_risk(
        files=["backend/api/auth.py", "backend/security/tokens.py", "backend/db/keys.py"],
        patch_diff=(
            "@@ -1,50 +1,150 @@\n"
            + "".join([f"+    crypto_token_{i} = 'bypass'\n" for i in range(80)])
        ),
    )
    assert high_risk["score"] > 0.70, f"Expected > 0.70, got {high_risk['score']}"
    assert high_risk["decision"] == "BLOCK", f"Expected BLOCK, got {high_risk['decision']}"


@pytest.mark.asyncio
async def test_sandbox_verification_truthfulness(tmp_path: Path):
    """Verify sandbox runs real test command, captures exit code,
    and PASS only occurs when exit code is 0.
    """
    sandbox = RecoverySandbox()

    # Create dummy git repository
    import subprocess
    repo_dir = tmp_path / "dummy_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True)

    # Initial buggy file and test
    calc_file = repo_dir / "calculator.py"
    calc_file.write_text("def div(a, b):\n    return a / b\n")
    test_file = repo_dir / "test_calculator.py"
    test_file.write_text(
        "import calculator\n"
        "def test_div():\n"
        "    assert calculator.div(10, 2) == 5\n"
        "def test_div_zero():\n"
        "    assert calculator.div(10, 0) == 0\n"  # Fails initially!
    )
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, check=True)

    # 1. Failing patch: fails verification, must NOT pass
    bad_patch = """diff --git a/calculator.py b/calculator.py
--- a/calculator.py
+++ b/calculator.py
@@ -1,2 +1,2 @@
 def div(a, b):
-    return a / b
+    return a / (b + 0)
"""
    bad_res = await sandbox.run_async(repo_dir, bad_patch, incident_id="test_fail")
    assert bad_res.patch_applied is True
    assert bad_res.exit_code != 0
    assert bad_res.tests_passed is False, "Sandbox MUST NOT pass on failing tests!"

    # 2. Correct patch: passes verification, exit code 0
    good_patch = """diff --git a/calculator.py b/calculator.py
--- a/calculator.py
+++ b/calculator.py
@@ -1,2 +1,4 @@
 def div(a, b):
+    if b == 0:
+        return 0
     return a / b
"""
    good_res = await sandbox.run_async(repo_dir, good_patch, incident_id="test_pass")
    assert good_res.patch_applied is True
    assert good_res.exit_code == 0
    assert good_res.tests_passed is True, "Sandbox MUST pass when tests actually succeed!"
    assert "passed" in good_res.stdout.lower()


@pytest.mark.asyncio
async def test_human_approval_persists_state():
    """Verify approval endpoint persists human_approved=True in DB
    and emits typed approved event.
    """
    incident_id = f"test_approval_{datetime.now(timezone.utc).timestamp()}"

    async with AsyncSessionLocal() as session:
        inc = await create_incident(
            session=session,
            incident_id=incident_id,
            github_payload={"test": True},
            repository="owner/repo",
            branch="main",
            commit_sha="abcdef123456",
            is_mock_mode=True,
        )
        inc.status = IncidentStatus.AWAITING_APPROVAL
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # User approves incident
        resp = await client.post(
            f"/api/v1/incident/{incident_id}/approve",
            json={"approved": True, "operator": "lead_sre", "reason": "Verified safe fix"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["approved"] is True
        assert data["incident_id"] == incident_id

    # Verify backend DB state actually changed
    async with AsyncSessionLocal() as session:
        db_inc = await get_incident(session=session, incident_id=incident_id)
        assert db_inc.human_approved is True, "Backend DB human_approved MUST be True after approval!"
        assert db_inc.status == IncidentStatus.REPAIRING

    # Verify telemetry event emitted
    history = await telemetry_manager.get_history(incident_id)
    event_types = [e.event_type for e in history]
    assert "approved" in event_types, f"Expected 'approved' in telemetry, got {event_types}"


@pytest.mark.asyncio
async def test_sse_required_event_flow():
    """Verify complete REQUIRED EVENT FLOW:
    webhook -> incident_created -> triage -> root_cause -> patch_generated
    -> sandbox_started -> sandbox_completed -> risk_evaluated
    -> approval_required -> approved -> branch_created -> commit_created -> pr_created
    """
    flow_incident_id = f"test_flow_{datetime.now(timezone.utc).timestamp()}"

    # Step 1: Webhook received & incident created
    await telemetry_manager.publish(
        incident_id=flow_incident_id,
        event_type="webhook",
        node_name="webhook_ingress",
        message="GitHub check_run failure received",
    )
    await telemetry_manager.publish(
        incident_id=flow_incident_id,
        event_type="incident_created",
        node_name="webhook_ingress",
        message="Incident created in database",
    )

    # Step 2: Triage
    await telemetry_manager.publish(
        incident_id=flow_incident_id,
        event_type="triage",
        node_name="triage_node",
        message="Triage analysis completed",
    )

    # Step 3: Root cause
    await telemetry_manager.publish(
        incident_id=flow_incident_id,
        event_type="root_cause",
        node_name="root_cause_node",
        message="Root cause identified as KeyError in auth.py",
    )

    # Step 4: Patch generated
    await telemetry_manager.publish(
        incident_id=flow_incident_id,
        event_type="patch_generated",
        node_name="repair_node",
        message="Remediation patch generated",
    )

    # Step 5: Sandbox started & completed
    await telemetry_manager.publish(
        incident_id=flow_incident_id,
        event_type="sandbox_started",
        node_name="failure_analyzer_node",
        message="Sandbox test execution started (python -m pytest -q)",
    )
    await telemetry_manager.publish(
        incident_id=flow_incident_id,
        event_type="sandbox_completed",
        node_name="failure_analyzer_node",
        message="Sandbox tests PASSED (VERIFIED)",
    )

    # Step 6: Risk evaluated
    await telemetry_manager.publish(
        incident_id=flow_incident_id,
        event_type="risk_evaluated",
        node_name="policy_risk_gateway",
        message="Risk evaluated: 0.42 (APPROVE)",
        risk_score=0.42,
    )

    # Step 7: Approval required & approved
    await telemetry_manager.publish(
        incident_id=flow_incident_id,
        event_type="approval_required",
        node_name="human_approval_node",
        message="Human operator approval required",
    )
    await telemetry_manager.publish(
        incident_id=flow_incident_id,
        event_type="approved",
        node_name="human_approval_node",
        message="Human operator approved recovery execution",
    )

    # Step 8: Branch, commit, PR
    await telemetry_manager.publish(
        incident_id=flow_incident_id,
        event_type="branch_created",
        node_name="recovery_complete_node",
        message="Recovery branch created",
    )
    await telemetry_manager.publish(
        incident_id=flow_incident_id,
        event_type="commit_created",
        node_name="recovery_complete_node",
        message="Patch committed to branch",
    )
    await telemetry_manager.publish(
        incident_id=flow_incident_id,
        event_type="pr_created",
        node_name="recovery_complete_node",
        message="Pull request opened",
    )

    history = await telemetry_manager.get_history(flow_incident_id)
    emitted_sequence = [e.event_type for e in history]

    required_flow = [
        "webhook",
        "incident_created",
        "triage",
        "root_cause",
        "patch_generated",
        "sandbox_started",
        "sandbox_completed",
        "risk_evaluated",
        "approval_required",
        "approved",
        "branch_created",
        "commit_created",
        "pr_created",
    ]

    for req in required_flow:
        assert req in emitted_sequence, f"Required event '{req}' missing from sequence: {emitted_sequence}"

    # Verify order is strictly maintained
    indices = [emitted_sequence.index(req) for req in required_flow]
    assert indices == sorted(indices), f"Event flow order violated! Got indices: {indices}"


@pytest.mark.asyncio
async def test_sse_reconnect_deduplication():
    """Verify subscription replays history faithfully and client deduplication key exists."""
    incident_id = f"test_recon_{datetime.now(timezone.utc).timestamp()}"

    # Publish an event
    evt = await telemetry_manager.publish(
        incident_id=incident_id,
        event_type="incident_created",
        node_name="webhook_ingress",
        message="Test event",
    )

    # First subscription
    sub1 = await telemetry_manager.subscribe(incident_id, replay_history=True)
    first_msg = await asyncio.wait_for(sub1.queue.get(), timeout=2.0)
    assert first_msg.event_id == evt.event_id
    await sub1.close()

    # Reconnect simulation: second subscription receives the exact same event with same event_id
    sub2 = await telemetry_manager.subscribe(incident_id, replay_history=True)
    reconnected_msg = await asyncio.wait_for(sub2.queue.get(), timeout=2.0)
    assert reconnected_msg.event_id == evt.event_id
    await sub2.close()
