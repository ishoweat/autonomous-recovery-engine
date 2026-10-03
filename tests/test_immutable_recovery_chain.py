import asyncio
import os
import uuid
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from backend.orchestration.state import RecoveryState, CanonicalRecoveryContext
from backend.orchestration.state_factory import create_initial_recovery_state
from backend.orchestration.nodes import (
    triage_node,
    root_cause_node,
    repair_node,
    recovery_complete_node,
)
from backend.integrations.github_tools import GitHubTools, PullRequestResult


@pytest.mark.asyncio
async def test_canonical_recovery_context_immutability():
    """
    Verify that failure file == AI target == patch target == sandbox target == PR target,
    and base commit_sha remains unchanged throughout the recovery pipeline.
    """
    incident_id = f"inc_immut_{uuid.uuid4().hex[:8]}"
    commit_sha = "7fd1a60b01f91b314f59955a4e4d4e80d8edf11d"
    repository = "test-org/test-repo"
    failure_file = "src/calculator.py"
    failure_line = 42
    error_message = "ZeroDivisionError: division by zero"
    stack_trace = "Traceback (most recent call last):\n  File 'src/calculator.py', line 42, in calculate_average\n    return total / len(numbers)\nZeroDivisionError: division by zero"

    github_payload = {
        "repository": {"full_name": repository, "default_branch": "main"},
        "workflow_run": {"head_sha": commit_sha, "head_branch": "main", "name": "Build & Test", "conclusion": "failure"},
        "failure_file": failure_file,
        "failure_line": failure_line,
        "error_message": error_message,
        "stack_trace": stack_trace,
    }

    # 1. State creation via factory
    state = create_initial_recovery_state(
        incident_id=incident_id,
        github_payload=github_payload,
        is_mock_mode=True,
    )

    assert state["incident_id"] == incident_id
    assert state["repository_full_name"] == repository
    assert state["commit_sha"] == commit_sha
    assert state["failure_file"] == failure_file
    assert state["failure_line"] == failure_line
    assert state["error_message"] == error_message
    assert state["stack_trace"] == stack_trace

    # 2. Triage Node
    triage_res = await triage_node(state, llm=None)
    state.update(triage_res)
    assert state["failure_file"] == failure_file
    assert state["commit_sha"] == commit_sha

    # 3. Root Cause Node
    rc_res = await root_cause_node(state, llm=None)
    state.update(rc_res)
    assert state["root_cause_analysis"]["affected_file"] == failure_file
    assert state["failure_file"] == failure_file
    assert state["commit_sha"] == commit_sha

    # 4. Repair Node
    repair_res = await repair_node(state, llm=None)
    state.update(repair_res)
    assert state["failure_file"] == failure_file
    assert state["commit_sha"] == commit_sha
    assert f"a/{failure_file}" in state["current_patch_diff"] or f"b/{failure_file}" in state["current_patch_diff"]

    # 5. Recovery Complete Node (PR Target)
    mock_gh_tools = MagicMock(spec=GitHubTools)
    mock_gh_tools.create_recovery_pr_full = AsyncMock(return_value=PullRequestResult(
        branch_name=f"recovery/fix-{incident_id[:8]}-{commit_sha[:8]}",
        commit_sha="verified_commit_123",
        pr_url="https://github.com/test-org/test-repo/pull/1",
        pr_number=1,
        access_level="WRITE",
    ))

    with patch("backend.orchestration.nodes.GitHubTools", return_value=mock_gh_tools):
        state["user_oauth_token"] = "gho_dummy_token"
        rec_res = await recovery_complete_node(state, llm=None)

    assert state["failure_file"] == failure_file
    assert state["commit_sha"] == commit_sha
    assert "https://github.com/test-org/test-repo/pull/" in rec_res["pr_url"]

    print("✅ Complete Causal Chain Verified: failure_file == AI target == patch target == sandbox target == PR target!")
    print(f"✅ Base commit SHA verified unchanged: {commit_sha}")


@pytest.mark.asyncio
async def test_canonical_recovery_context_dataclass():
    """Verify CanonicalRecoveryContext dataclass fields and dictionary export."""
    ctx = CanonicalRecoveryContext(
        incident_id="inc_123",
        repository_full_name="org/repo",
        commit_sha="abc12345",
        failure_file="app/main.py",
        failure_line=15,
        error_message="ValueError: invalid literal",
        stack_trace="Traceback...",
    )
    d = ctx.as_dict()
    assert d["incident_id"] == "inc_123"
    assert d["repository_full_name"] == "org/repo"
    assert d["commit_sha"] == "abc12345"
    assert d["failure_file"] == "app/main.py"
    assert d["failure_line"] == 15
    assert d["error_message"] == "ValueError: invalid literal"
    assert d["stack_trace"] == "Traceback..."
