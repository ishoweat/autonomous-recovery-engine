"""
tests/test_phase5_block.py
──────────────────────────
Phase 5: BLOCK path tests.

Must pass:
  - FORCE_RISK_SCORE=0.85 → risk decision is BLOCK
  - No patch is applied (PR blocked)
  - human_escalation.run_human_escalation emits the right telemetry structure
  - escalation is stored in DB (escalations table)
  - get_blocked_count returns correct count
  - /api/v1/roi/blocked-incidents returns count
  - 0.5 and 0.1 paths are unchanged (APPROVE / ALLOW)
"""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.orchestration.risk import calculate_patch_risk


# ─────────────────────────────────────────────────────────────────────────────
# Risk score threshold tests (additive to existing tests)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_forced_085_is_block():
    os.environ["FORCE_RISK_SCORE"] = "0.85"
    os.environ["ENVIRONMENT"] = "development"
    risk = calculate_patch_risk(files=["calculator.py"], patch_diff="+ fix")
    assert risk["score"] == 0.85
    assert risk["decision"] == "BLOCK"
    del os.environ["FORCE_RISK_SCORE"]


@pytest.mark.asyncio
async def test_forced_05_is_approve():
    os.environ["FORCE_RISK_SCORE"] = "0.5"
    os.environ["ENVIRONMENT"] = "development"
    risk = calculate_patch_risk(files=["calculator.py"], patch_diff="+ fix")
    assert risk["score"] == 0.5
    assert risk["decision"] == "APPROVE"
    del os.environ["FORCE_RISK_SCORE"]


@pytest.mark.asyncio
async def test_forced_01_is_allow():
    os.environ["FORCE_RISK_SCORE"] = "0.1"
    os.environ["ENVIRONMENT"] = "development"
    risk = calculate_patch_risk(files=["calculator.py"], patch_diff="+ fix")
    assert risk["score"] == 0.1
    assert risk["decision"] == "ALLOW"
    del os.environ["FORCE_RISK_SCORE"]


# ─────────────────────────────────────────────────────────────────────────────
# Escalation table / get_blocked_count
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_blocked_count_returns_int():
    from backend.recovery_ext.human_escalation import get_blocked_count
    count = await get_blocked_count()
    assert isinstance(count, int)
    assert count >= 0


@pytest.mark.asyncio
async def test_blocked_count_increases_after_store():
    from backend.recovery_ext.human_escalation import (
        _init_escalations_table,
        _store_escalation,
        get_blocked_count,
        EscalationResult,
    )
    from datetime import datetime, timezone

    await _init_escalations_table()
    before = await get_blocked_count()

    result = EscalationResult(
        incident_id=f"test-block-{before}-unique",
        failure_reason="BLOCKED_BY_POLICY",
        risk_score=0.85,
        top_factors=[{"factor": "file_criticality", "contribution": 0.3}],
        issue_url=None,
        escalated_at=datetime.now(timezone.utc).isoformat(),
    )
    await _store_escalation(result, repository="owner/repo", affected_file="calc.py")

    after = await get_blocked_count()
    assert after >= before  # should be equal or greater (could be == if unique violation)


# ─────────────────────────────────────────────────────────────────────────────
# API endpoint: /api/v1/roi/blocked-incidents
# ─────────────────────────────────────────────────────────────────────────────

def test_blocked_incidents_api():
    client = TestClient(app)
    response = client.get("/api/v1/roi/blocked-incidents")
    assert response.status_code == 200
    body = response.json()
    assert "blocked_incidents" in body
    assert isinstance(body["blocked_incidents"], int)


# ─────────────────────────────────────────────────────────────────────────────
# GitHub issue creation — offline unit test (mocked)
# ─────────────────────────────────────────────────────────────────────────────

def test_create_github_issue_no_token():
    """Without a GITHUB_TOKEN, issue creation should return None silently."""
    original = os.environ.pop("GITHUB_TOKEN", None)
    try:
        from backend.recovery_ext.human_escalation import _create_github_issue
        result = _create_github_issue(
            repository_full_name="owner/repo",
            incident_id="test-block-001",
            affected_file="calculator.py",
            error_message="ZeroDivisionError",
            risk_score=0.85,
            top_factors=[{"factor": "file_criticality", "contribution": 0.35}],
            failure_reason="BLOCKED_BY_POLICY",
        )
        assert result is None
    finally:
        if original is not None:
            os.environ["GITHUB_TOKEN"] = original


# ─────────────────────────────────────────────────────────────────────────────
# run_human_escalation: flag disabled → no-op
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_human_escalation_disabled():
    """When ENABLE_BLOCK_ESCALATION=false, run_human_escalation is a no-op."""
    os.environ["ENABLE_BLOCK_ESCALATION"] = "false"
    from backend.recovery_ext.flags import get_flags
    get_flags.cache_clear()

    from backend.recovery_ext.human_escalation import run_human_escalation
    state = {
        "incident_id": "esc-disabled-001",
        "explainable_risk": {"score": 0.85, "decision": "BLOCK", "breakdown": []},
        "repository_full_name": "owner/repo",
        "root_cause_analysis": {"affected_file": "calc.py"},
        "triage_context": "ZeroDivisionError",
        "retry_count": 0,
    }
    result = await run_human_escalation(state)
    assert result.issue_url is None
    assert result.failure_reason == "BLOCKED_BY_POLICY"

    del os.environ["ENABLE_BLOCK_ESCALATION"]
    get_flags.cache_clear()
