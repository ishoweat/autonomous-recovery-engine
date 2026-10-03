"""
tests/test_phase6_sandbox.py
───────────────────────────────
Phase 6: Sandbox hardening, auto-merge, and scavenger.
"""
from __future__ import annotations

import os
import pytest
from backend.recovery_ext.sandbox_policy import get_policy_kwargs
from backend.recovery_ext.auto_merge import attempt_auto_merge, AutoMergeResult


@pytest.mark.asyncio
async def test_policy_kwargs_when_disabled():
    """When hardening is off, we only get the label."""
    kwargs = get_policy_kwargs(hardening_enabled=False)
    assert list(kwargs.keys()) == ["labels"]
    assert "are-sandbox" in kwargs["labels"]


@pytest.mark.asyncio
async def test_policy_kwargs_when_enabled():
    """When hardening is on, we get all the security constraints."""
    os.environ["RECOVERY_SANDBOX_MEMORY_LIMIT"] = "256m"
    kwargs = get_policy_kwargs(hardening_enabled=True)
    assert kwargs["network_mode"] == "none"
    assert kwargs["mem_limit"] == "256m"
    assert "nano_cpus" in kwargs
    assert "labels" in kwargs
    assert "are-sandbox" in kwargs["labels"]


@pytest.mark.asyncio
async def test_auto_merge_disabled():
    """If ENABLE_AUTO_MERGE is false, attempt_auto_merge is a no-op."""
    os.environ["ENABLE_AUTO_MERGE"] = "false"
    from backend.recovery_ext.flags import get_flags
    get_flags.cache_clear()

    res = await attempt_auto_merge(
        state={"action_decision": "ALLOW"},
        pr_url="http://github.com/org/repo/pull/1",
        pr_number=1,
        repository_full_name="org/repo",
        incident_id="demo",
    )
    assert not res.merged
    assert res.method == "skipped"


@pytest.mark.asyncio
async def test_auto_merge_block_decision():
    """If decision is BLOCK, auto-merge skips."""
    os.environ["ENABLE_AUTO_MERGE"] = "true"
    from backend.recovery_ext.flags import get_flags
    get_flags.cache_clear()

    res = await attempt_auto_merge(
        state={"action_decision": "BLOCK"},
        pr_url="http://github.com/org/repo/pull/1",
        pr_number=1,
        repository_full_name="org/repo",
        incident_id="demo",
    )
    assert not res.merged
    assert res.method == "skipped"
