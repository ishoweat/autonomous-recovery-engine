# backend/orchestration/guards.py

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend.orchestration.state import RecoveryState
from backend.services.telemetry import telemetry_manager


MAX_RETRIES = 3
RISK_BLOCK_THRESHOLD = 0.7
MOCK_MAX_RUNTIME_SECONDS = 5.0


class RecoveryEscalation(RuntimeError):
    """Raised when automated recovery must stop and reach a human."""


@dataclass(slots=True, frozen=True)
class GuardDecision:
    allowed: bool
    escalate: bool
    reason: str


def validate_retry_budget(
    retry_count: int,
) -> GuardDecision:
    if retry_count < 0:
        return GuardDecision(
            allowed=False,
            escalate=True,
            reason="retry_count cannot be negative",
        )

    if retry_count >= MAX_RETRIES:
        return GuardDecision(
            allowed=False,
            escalate=True,
            reason=(
                f"retry ceiling reached: "
                f"{retry_count}/{MAX_RETRIES}"
            ),
        )

    return GuardDecision(
        allowed=True,
        escalate=False,
        reason=(
            f"retry budget available: "
            f"{retry_count}/{MAX_RETRIES}"
        ),
    )


def validate_risk_budget(
    score: float,
) -> GuardDecision:
    if not 0.0 <= score <= 1.0:
        return GuardDecision(
            allowed=False,
            escalate=True,
            reason=f"invalid risk score: {score}",
        )

    if score > RISK_BLOCK_THRESHOLD:
        return GuardDecision(
            allowed=False,
            escalate=True,
            reason=(
                f"risk score {score:.4f} exceeds "
                f"hard block threshold "
                f"{RISK_BLOCK_THRESHOLD:.4f}"
            ),
        )

    return GuardDecision(
        allowed=True,
        escalate=False,
        reason=(
            f"risk score {score:.4f} is below "
            f"hard block threshold"
        ),
    )


def evaluate_recovery_guards(
    state: RecoveryState,
) -> GuardDecision:
    """
    Central hard gate.

    Escalation occurs if either:
      retry_count >= 3
      risk score > 0.7
    """

    retry_decision = validate_retry_budget(
        state["retry_count"]
    )

    if retry_decision.escalate:
        return retry_decision

    risk = state["explainable_risk"]

    score = float(
        risk.get(
            "score",
            1.0,
        )
    )

    risk_decision = validate_risk_budget(
        score
    )

    if risk_decision.escalate:
        return risk_decision

    return GuardDecision(
        allowed=True,
        escalate=False,
        reason=(
            "Recovery satisfies retry and risk "
            "safety constraints"
        ),
    )


def build_postmortem(
    state: RecoveryState,
    *,
    reason: str,
) -> dict[str, Any]:
    """
    Produce a structured incident post-mortem event.

    No LLM is involved in this function: escalation records must remain
    deterministic and available even when the model or external services
    are unavailable.
    """

    risk = state["explainable_risk"]

    return {
        "incident_id": state["incident_id"],
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "classification": "HUMAN ESCALATION",
        "reason": reason,
        "retry_count": state["retry_count"],
        "risk_score": float(
            risk.get("score", 1.0)
        ),
        "risk_decision": risk.get(
            "decision",
            "BLOCK",
        ),
        "triage_context": state["triage_context"],
        "root_cause_analysis": state[
            "root_cause_analysis"
        ],
        "test_results": state[
            "test_results"
        ],
        "patch_generated": bool(
            state["current_patch_diff"]
        ),
        "human_approved": state[
            "human_approved"
        ],
        "pr_created": bool(
            state["pr_url"]
        ),
    }


def escalate_state(
    state: RecoveryState,
    *,
    reason: str,
) -> RecoveryState:
    """
    Convert a running recovery state into a terminal escalation state.
    """

    postmortem = build_postmortem(
        state,
        reason=reason,
    )

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(
            telemetry_manager.publish(
                incident_id=state["incident_id"],
                event_type="escalated",
                node_name="guards",
                message="Recovery escalated to human operator",
                metadata={
                    "classification": "HUMAN ESCALATION",
                    "postmortem": postmortem,
                },
                risk_score=float(
                    state["explainable_risk"].get(
                        "score",
                        1.0,
                    )
                ),
                retry_count=state["retry_count"],
            )
        )
    except RuntimeError:
        pass

    updated = dict(state)

    updated["action_decision"] = "BLOCK"

    return updated  # type: ignore[return-value]


def guarded_transition(
    state: RecoveryState,
) -> RecoveryState:
    decision = evaluate_recovery_guards(
        state
    )

    if decision.escalate:
        return escalate_state(
            state,
            reason=decision.reason,
        )

    return state


async def deterministic_mock_recovery(
    state: RecoveryState,
) -> RecoveryState:
    """
    Deterministic fallback used for demos and controlled CI.

    Guarantees:
      * no Nebius request
      * no Docker execution
      * no GitHub mutation
      * <5 second execution budget
      * same target KeyError regression every run
    """

    started = time.monotonic()

    current = dict(state)

    incident_id = current[
        "incident_id"
    ]

    await asyncio.sleep(0)

    current["triage_context"] = (
        "Mock SRE triage: CI reported "
        "KeyError: 'user_id' in "
        "backend/api/auth.py. "
        "Payload validation is missing."
    )

    if time.monotonic() - started >= MOCK_MAX_RUNTIME_SECONDS:
        raise TimeoutError(
            "Mock recovery exceeded five-second budget"
        )

    current[
        "root_cause_analysis"
    ] = {
        "exception": "KeyError: 'user_id'",
        "file": "backend/api/auth.py",
        "line_pattern": "payload['user_id']",
        "root_cause": (
            "The authentication handler indexes user_id "
            "directly without validating that the key exists."
        ),
        "regression_vector": (
            "request payload omits user_id"
        ),
    }

    current[
        "explainable_risk"
    ] = {
        "score": 0.41,
        "breakdown": [
            {
                "factor": "file_criticality",
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
                    "The demonstration patch changes one "
                    "application file."
                ),
            },
            {
                "factor": "test_coverage",
                "value": 0.10,
                "weight": 0.40,
                "contribution": 0.04,
                "explanation": (
                    "A regression test validates missing user_id."
                ),
            },
        ],
        "decision": "APPROVE",
    }

    current[
        "action_decision"
    ] = "APPROVE"

    current[
        "current_patch_diff"
    ] = (
        "--- a/backend/api/auth.py\n"
        "+++ b/backend/api/auth.py\n"
        "@@ -1,7 +1,12 @@\n"
        " def authenticate(payload):\n"
        "-    user_id = payload['user_id']\n"
        "+    if 'user_id' not in payload:\n"
        "+        raise ValueError('user_id is required')\n"
        "+\n"
        "+    user_id = payload['user_id']\n"
        "     if not isinstance(user_id, str):\n"
        "         raise ValueError('user_id must be a string')\n"
    )

    if time.monotonic() - started >= MOCK_MAX_RUNTIME_SECONDS:
        raise TimeoutError(
            "Mock recovery exceeded five-second budget"
        )

    current[
        "test_results"
    ] = {
        "stdout": (
            "================ test session ================\n"
            "3 passed in 0.21s\n"
            "Target regression: fixed\n"
        ),
        "stderr": "",
        "exit_code": 0,
    }

    current[
        "retry_count"
    ] = 0

    await telemetry_manager.publish(
        incident_id=incident_id,
        event_type="sandbox_completed",
        node_name="mock_sandbox",
        message=(
            "Mock sandbox completed successfully"
        ),
        metadata={
            "mock": True,
            "regression": "KeyError: 'user_id'",
        },
        retry_count=0,
    )

    if time.monotonic() - started >= MOCK_MAX_RUNTIME_SECONDS:
        raise TimeoutError(
            "Mock recovery exceeded five-second budget"
        )

    return current  # type: ignore[return-value]


async def run_with_mock_fallback(
    state: RecoveryState,
    *,
    external_runner,
) -> RecoveryState:
    """
    Use deterministic mock mode directly when requested.

    In non-mock mode, external_runner remains responsible for the actual
    LangGraph/Nemotron/sandbox pipeline. If that external path is
    unavailable, callers can explicitly invoke this fallback.
    """

    if state.get("is_mock_mode"):
        return await deterministic_mock_recovery(
            state
        )

    try:
        return await external_runner(
            state
        )
    except (
        ConnectionError,
        TimeoutError,
    ) as exc:
        await telemetry_manager.publish(
            incident_id=state["incident_id"],
            event_type="error",
            node_name="runtime_guard",
            message=(
                "External recovery dependency unavailable; "
                "switching to deterministic mock fallback"
            ),
            metadata={
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )

        return await deterministic_mock_recovery(
            state
        )


def assert_runtime_safe(
    state: RecoveryState,
) -> None:
    """
    Fail closed before an execution-sensitive node.

    This function is intentionally synchronous so it can be called before
    Docker, GitHub, or model operations.
    """

    decision = evaluate_recovery_guards(
        state
    )

    if decision.escalate:
        raise RecoveryEscalation(
            decision.reason
        )
