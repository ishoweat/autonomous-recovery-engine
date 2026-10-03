# tests/test_phase7.py

from __future__ import annotations

import pytest

from sandbox.vulnerable_app.auth import authenticate
from backend.tools.sandbox_cleanup import (
    SandboxSecurityConfig,
    purge_orphaned_sandboxes,
    startup_sandbox_cleanup,
)
from backend.orchestration.guards import (
    GuardDecision,
    RecoveryEscalation,
    assert_runtime_safe,
    build_postmortem,
    deterministic_mock_recovery,
    escalate_state,
    evaluate_recovery_guards,
    guarded_transition,
    run_with_mock_fallback,
    validate_retry_budget,
    validate_risk_budget,
)
from backend.orchestration.routing import recovery_route
from backend.orchestration.state import RecoveryState


def test_vulnerable_app_key_error_reproduction() -> None:
    """
    Verify vulnerable app reproduces KeyError: 'user_id' on missing key,
    and returns valid auth dict when present.
    """

    res = authenticate({"user_id": "alice"})
    assert res == {"authenticated": True, "user_id": "alice"}

    with pytest.raises(KeyError, match="user_id"):
        authenticate({})

    with pytest.raises(ValueError, match="user_id"):
        authenticate({"user_id": ""})


def test_sandbox_security_config_validations() -> None:
    """
    Verify immutable security policy constraints.
    """

    cfg = SandboxSecurityConfig()
    assert cfg.network_mode == "none"
    assert cfg.mem_limit == "512m"
    assert cfg.cpu_count == 1.0
    assert cfg.timeout_seconds == 30

    with pytest.raises(ValueError, match="network_mode='none'"):
        SandboxSecurityConfig(network_mode="bridge")

    with pytest.raises(ValueError, match="512m memory limit"):
        SandboxSecurityConfig(mem_limit="1024m")

    with pytest.raises(ValueError, match="exactly one CPU"):
        SandboxSecurityConfig(cpu_count=2.0)

    with pytest.raises(ValueError, match="between 1 and 30"):
        SandboxSecurityConfig(timeout_seconds=60)


def test_validate_retry_budget_ceiling() -> None:
    """
    Verify retry ceiling is capped at 3 attempts.
    """

    d0 = validate_retry_budget(0)
    assert d0.allowed is True and d0.escalate is False

    d2 = validate_retry_budget(2)
    assert d2.allowed is True and d2.escalate is False

    d3 = validate_retry_budget(3)
    assert d3.allowed is False and d3.escalate is True
    assert "retry ceiling reached" in d3.reason

    d_neg = validate_retry_budget(-1)
    assert d_neg.allowed is False and d_neg.escalate is True


def test_validate_risk_budget_threshold() -> None:
    """
    Verify hard block threshold at 0.7.
    """

    d_low = validate_risk_budget(0.3)
    assert d_low.allowed is True and d_low.escalate is False

    d_high = validate_risk_budget(0.71)
    assert d_high.allowed is False and d_high.escalate is True
    assert "exceeds hard block threshold" in d_high.reason

    d_invalid = validate_risk_budget(1.5)
    assert d_invalid.allowed is False and d_invalid.escalate is True


@pytest.fixture
def base_state() -> RecoveryState:
    return {
        "incident_id": "phase7-test-incident",
        "github_payload": {},
        "is_mock_mode": True,
        "triage_context": "",
        "root_cause_analysis": {},
        "explainable_risk": {
            "score": 0.2,
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


def test_evaluate_recovery_guards(base_state: RecoveryState) -> None:
    decision = evaluate_recovery_guards(base_state)
    assert decision.allowed is True
    assert decision.escalate is False

    state_high_retries = dict(base_state)
    state_high_retries["retry_count"] = 3
    dec_retries = evaluate_recovery_guards(state_high_retries)  # type: ignore[arg-type]
    assert dec_retries.escalate is True

    state_high_risk = dict(base_state)
    state_high_risk["explainable_risk"] = {"score": 0.85, "breakdown": [], "decision": "BLOCK"}
    dec_risk = evaluate_recovery_guards(state_high_risk)  # type: ignore[arg-type]
    assert dec_risk.escalate is True


def test_build_postmortem_and_escalate_state(base_state: RecoveryState) -> None:
    pm = build_postmortem(base_state, reason="Test escalation")
    assert pm["incident_id"] == "phase7-test-incident"
    assert pm["classification"] == "HUMAN ESCALATION"
    assert pm["reason"] == "Test escalation"

    escalated = escalate_state(base_state, reason="Test escalation")
    assert escalated["action_decision"] == "BLOCK"


@pytest.mark.asyncio
async def test_deterministic_mock_recovery(base_state: RecoveryState) -> None:
    result = await deterministic_mock_recovery(base_state)
    assert "KeyError: 'user_id'" in result["triage_context"]
    assert result["root_cause_analysis"]["exception"] == "KeyError: 'user_id'"
    assert result["test_results"]["exit_code"] == 0
    assert result["current_patch_diff"] != ""
    assert result["action_decision"] == "APPROVE"


@pytest.mark.asyncio
async def test_run_with_mock_fallback(base_state: RecoveryState) -> None:
    async def failing_runner(s: RecoveryState) -> RecoveryState:
        raise ConnectionError("Nebius connection failed")

    # In mock mode, returns mock directly
    res_mock = await run_with_mock_fallback(base_state, external_runner=failing_runner)
    assert res_mock["test_results"]["exit_code"] == 0

    # In non-mock mode, falls back to mock recovery on ConnectionError
    non_mock_state = dict(base_state)
    non_mock_state["is_mock_mode"] = False
    res_fallback = await run_with_mock_fallback(non_mock_state, external_runner=failing_runner)  # type: ignore[arg-type]
    assert res_fallback["test_results"]["exit_code"] == 0


def test_assert_runtime_safe(base_state: RecoveryState) -> None:
    assert_runtime_safe(base_state)

    unsafe_state = dict(base_state)
    unsafe_state["retry_count"] = 5
    with pytest.raises(RecoveryEscalation, match="retry ceiling reached"):
        assert_runtime_safe(unsafe_state)  # type: ignore[arg-type]


def test_recovery_route_routing(base_state: RecoveryState) -> None:
    # Under limit -> repair_node
    assert recovery_route(base_state) == "repair_node"

    # Retry count >= 3 -> escalation_node
    retried_state = dict(base_state)
    retried_state["retry_count"] = 3
    assert recovery_route(retried_state) == "escalation_node"  # type: ignore[arg-type]

    # Score > 0.7 -> escalation_node
    risky_state = dict(base_state)
    risky_state["explainable_risk"] = {"score": 0.9, "breakdown": [], "decision": "BLOCK"}
    assert recovery_route(risky_state) == "escalation_node"  # type: ignore[arg-type]


def test_startup_sandbox_cleanup() -> None:
    # Startup cleanup should complete without error
    removed = startup_sandbox_cleanup()
    assert isinstance(removed, int)
