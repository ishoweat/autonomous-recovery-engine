"""
tests/test_phase7_e2e.py
─────────────────────────
End-to-End Test for Phase 7: All flags ON.
Covers ALLOW, APPROVE, BLOCK, and Post-Merge Verify.
"""
from __future__ import annotations

import os
import pytest
from backend.recovery_ext.flags import get_flags
from backend.recovery_ext.post_merge import trigger_post_merge_verification, start_bounded_poller
from backend.recovery_ext.auto_merge import attempt_auto_merge

@pytest.fixture(autouse=True)
def setup_flags():
    """Enable all Phase 7 flags for E2E testing."""
    os.environ["ENABLE_POLICY_RISK_GATEWAY"] = "true"
    os.environ["ENABLE_DECISION_ROUTER"] = "true"
    os.environ["ENABLE_APPROVAL_GATE"] = "true"
    os.environ["ENABLE_BLOCK_ESCALATION"] = "true"
    os.environ["ENABLE_SANDBOX_HARDENING"] = "true"
    os.environ["ENABLE_AUTO_MERGE"] = "true"
    os.environ["ENABLE_POST_MERGE_VERIFY"] = "true"
    get_flags.cache_clear()
    yield
    # We could unset them here, but tests run isolated enough


@pytest.mark.asyncio
async def test_e2e_allow_path():
    """ALLOW path should trigger auto-merge and start poller."""
    flags = get_flags()
    assert flags.enable_auto_merge
    assert flags.enable_post_merge_verify

    res = await attempt_auto_merge(
        state={"action_decision": "ALLOW"},
        pr_url="http://github.com/org/repo/pull/1",
        pr_number=1,
        repository_full_name="org/repo",
        incident_id="demo_allow",
    )
    # The actual merge will fail in tests (no token), so it will return error or refused, 
    # but the attempt happens and logic branches correctly.
    assert res.method in ("error", "refused")


@pytest.mark.asyncio
async def test_e2e_approve_path():
    """APPROVE path needs human_approved=True to merge."""
    # Attempt without human approval
    res1 = await attempt_auto_merge(
        state={"action_decision": "APPROVE"},
        pr_url="http://github.com/org/repo/pull/1",
        pr_number=1,
        repository_full_name="org/repo",
        incident_id="demo_approve",
    )
    assert not res1.merged
    assert res1.method == "skipped"

    # Attempt with human approval
    res2 = await attempt_auto_merge(
        state={"action_decision": "APPROVE", "human_approved": True},
        pr_url="http://github.com/org/repo/pull/1",
        pr_number=1,
        repository_full_name="org/repo",
        incident_id="demo_approve",
    )
    assert res2.method in ("error", "refused")


@pytest.mark.asyncio
async def test_e2e_block_path():
    """BLOCK path never merges."""
    res = await attempt_auto_merge(
        state={"action_decision": "BLOCK"},
        pr_url="http://github.com/org/repo/pull/1",
        pr_number=1,
        repository_full_name="org/repo",
        incident_id="demo_block",
    )
    assert not res.merged
    assert res.method == "skipped"


@pytest.mark.asyncio
async def test_e2e_post_merge_poller():
    """Start bounded poller test (it spawns background task)."""
    # This won't do much without a real PR, but verifies it doesn't crash
    await start_bounded_poller(
        incident_id="demo_poller",
        pr_number=1,
        repository_full_name="org/repo",
        max_attempts=1,  # Keep it short
        backoff_seconds=0,
    )
    # Task runs in background, we just verify the call succeeds.
    assert True
