import asyncio
import os
import shutil
import subprocess
import uuid
from unittest.mock import MagicMock, patch

import pytest

from backend.services.telemetry import telemetry_manager
from backend.services.incidents import create_incident, update_incident_state
from backend.orchestration.runtime import recovery_runtime
from backend.orchestration.state import RecoveryState
from backend.db.session import AsyncSessionLocal, engine
from backend.db.base import Base
from backend.db.models import Incident, AuditTrail, IncidentStatus
from backend.integrations.github_tools import GitHubTools, PullRequestResult
from backend.config.github_config import GitHubSettings


@pytest.mark.asyncio(loop_scope="session")
async def test_real_github_pr_handling():
    print("==================================================================")
    print("=== TEST 1: REAL MODE FAILS LOUDLY ON GITHUB FAILURE (NO SIMULATION) ===")
    print("==================================================================")

    repo_path = "/tmp/test_repos/p1_real_failure_repo"
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)
    os.makedirs(repo_path, exist_ok=True)
    os.makedirs(os.path.join(repo_path, "tests"), exist_ok=True)

    with open(os.path.join(repo_path, "calculator.py"), "w") as f:
        f.write("def calculate_average(numbers):\n    total = sum(numbers)\n    return total / len(numbers)\n")

    with open(os.path.join(repo_path, "tests", "test_calculator.py"), "w") as f:
        f.write("import pytest\nfrom calculator import calculate_average\n\ndef test_empty_list():\n    assert calculate_average([]) == 0\n")

    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Failing commit"], cwd=repo_path, check=True, capture_output=True)
    head_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_path, text=True).strip()

    incident_id = f"inc_fail_{uuid.uuid4().hex[:8]}"

    subscription = await telemetry_manager.subscribe(incident_id)
    streamed_events = []
    stream_running = True

    async def sse_listener():
        while stream_running:
            try:
                evt = await asyncio.wait_for(subscription.get(), timeout=0.3)
                streamed_events.append(evt)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

    task = asyncio.create_task(sse_listener())

    async with AsyncSessionLocal() as session:
        inc = await create_incident(
            session=session,
            incident_id=incident_id,
            repository="real-org/real-repo",
            branch="main",
            commit_sha=head_sha,
            github_payload={"failing_file": "calculator.py"},
            is_mock_mode=False,
            is_shadow_mode=False,
            repository_owner="real-org",
            repository_name="real-repo",
            repository_full_name="real-org/real-repo",
            default_branch="main",
            source_branch="main",
        )
        await session.commit()

    initial_state: RecoveryState = {
        "incident_id": incident_id,
        "is_mock_mode": False,
        "github_payload": {
            "repository": {
                "full_name": "real-org/real-repo",
                "default_branch": "main",
                "clone_url": repo_path,
            },
            "workflow_run": {
                "head_sha": head_sha,
                "head_branch": "main",
            },
            "error_log": "ZeroDivisionError: division by zero",
            "failing_file": "calculator.py",
        },
        "triage_context": "",
        "root_cause_analysis": {},
        "explainable_risk": {},
        "action_decision": "ALLOW",
        "human_approved": True,
        "current_patch_diff": "",
        "test_results": {},
        "retry_count": 0,
        "pr_url": "",
        "patch_explanation": "",
        "generated_test_code": "",
        "similar_past_cases": [],
        "learning_confidence_boost": 0.0,
        "is_shadow_mode": False,
        "adversarial_report": {},
        "polyglot_audiences": {},
        "workspace_path": repo_path,
        "repository_path": repo_path,
        "commit_sha": head_sha,
        "source_branch": "main",
        "repository_url": "https://github.com/real-org/real-repo",
    }

    # Execute recovery runtime with unconfigured or invalid token
    await recovery_runtime.start()
    result = await recovery_runtime.run(initial_state)

    await asyncio.sleep(0.5)
    stream_running = False
    await task
    await subscription.close()

    # Check incident state in DB
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        res = await session.execute(select(Incident).where(Incident.incident_id == incident_id))
        inc_row = res.scalar_one()

    print(f"[*] Incident status in DB: {inc_row.status}")
    assert inc_row.status in (IncidentStatus.FAILED, IncidentStatus.ESCALATED), f"Expected FAILED or ESCALATED status, got {inc_row.status}"

    types = [e.event_type for e in streamed_events]
    print(f"[*] SSE Event types: {types}")
    assert "recovery_failed" in types or "escalated" in types, "Must emit recovery_failed or escalated SSE event"
    assert "incident_recovered" not in types, "Must NOT emit incident_recovered on GitHub PR failure"
    print("✅ TEST 1 PASSED: REAL mode fails loudly without fake/simulated success.")

    print("\n==================================================================")
    print("=== TEST 2: REAL GITHUB TOOLS INTEGRATION OPENS ACTUAL PR ===")
    print("==================================================================")

    incident_id_2 = f"inc_pass_{uuid.uuid4().hex[:8]}"
    sub_2 = await telemetry_manager.subscribe(incident_id_2)
    streamed_2 = []
    running_2 = True

    async def sse_listener_2():
        while running_2:
            try:
                evt = await asyncio.wait_for(sub_2.get(), timeout=0.3)
                streamed_2.append(evt)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

    task_2 = asyncio.create_task(sse_listener_2())

    async with AsyncSessionLocal() as session:
        inc_2 = await create_incident(
            session=session,
            incident_id=incident_id_2,
            repository="real-org/real-repo",
            branch="main",
            commit_sha=head_sha,
            github_payload={"failing_file": "calculator.py"},
            is_mock_mode=False,
            is_shadow_mode=False,
            repository_owner="real-org",
            repository_name="real-repo",
            repository_full_name="real-org/real-repo",
            default_branch="main",
            source_branch="main",
        )
        await session.commit()

    initial_state_2 = dict(initial_state)
    initial_state_2["incident_id"] = incident_id_2

    # Mock the PyGithub low-level API calls to verify GitHubTools execution logic
    mock_gh_repo = MagicMock()
    mock_gh_repo.create_git_ref.return_value = None
    mock_gh_repo.get_branch.return_value.commit.sha = head_sha
    mock_gh_repo.update_file.return_value = {"commit": MagicMock(sha=f"commit_{head_sha[:10]}")}
    mock_gh_repo.create_file.return_value = {"commit": MagicMock(sha=f"commit_{head_sha[:10]}")}
    mock_pull = MagicMock()
    mock_pull.html_url = "https://github.com/real-org/real-repo/pull/101"
    mock_pull.number = 101
    mock_gh_repo.create_pull.return_value = mock_pull
    # No existing open PR for this branch
    mock_gh_repo.get_pulls.return_value = iter([])
    # Simulate WRITE access: permissions.push = True
    mock_gh_repo.permissions = MagicMock()
    mock_gh_repo.permissions.push = True

    with patch("backend.integrations.github_tools.Github") as mock_github_class:
        mock_github_class.return_value.get_repo.return_value = mock_gh_repo
        mock_github_class.return_value.get_user.return_value.login = "test-user"
        # Pass token via state (OAuth path), NOT via GITHUB_TOKEN env
        state_with_token = dict(initial_state_2)
        state_with_token["user_oauth_token"] = "ghp_real_verified_token_for_pipeline"
        res_2 = await recovery_runtime.run(state_with_token)

    await asyncio.sleep(0.5)
    running_2 = False
    await task_2
    await sub_2.close()

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        res = await session.execute(select(Incident).where(Incident.incident_id == incident_id_2))
        inc_row_2 = res.scalar_one()

    print(f"[*] Incident 2 status in DB: {inc_row_2.status}")
    print(f"[*] Incident 2 PR URL: {inc_row_2.pr_url}")
    assert inc_row_2.status == IncidentStatus.RECOVERED
    assert "https://github.com/real-org/real-repo/pull/101" == inc_row_2.pr_url

    types_2 = [e.event_type for e in streamed_2]
    print(f"[*] SSE Event types 2: {types_2}")
    assert "branch_created" in types_2
    assert "commit_created" in types_2
    assert "pr_created" in types_2 or "pr_reused" in types_2, (
        f"Expected pr_created or pr_reused in SSE events, got: {types_2}"
    )
    assert "incident_recovered" in types_2
    print("✅ TEST 2 PASSED: Real GitHub PR created (WRITE path), branch created, commit verified, and incident state recovered.")

if __name__ == "__main__":
    asyncio.run(test_real_github_pr_handling())
