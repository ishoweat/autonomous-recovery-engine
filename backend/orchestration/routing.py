from __future__ import annotations

from typing import Literal

from backend.orchestration.state import RecoveryState


def route_after_risk(
    state: RecoveryState,
) -> Literal[
    "recovery_complete_node",
    "human_approval_node",
    "escalation_node",
]:
    """Route solely from the deterministic risk decision."""

    decision = state["action_decision"]
    from backend.recovery_ext.flags import get_flags
    flags = get_flags()

    if decision == "ALLOW":
        return "recovery_complete_node"

    if decision == "APPROVE":
        if flags.enable_approval_gate:
            return "human_approval_node"
        # Not enabled branch: preserves old behavior (previously went to human_approval_node)
        return "human_approval_node"

    if flags.enable_block_escalation:
        return "escalation_node"
    # Not enabled branch: preserves old behavior (previously went to escalation_node)
    return "escalation_node"


def route_after_approval(
    state: RecoveryState,
) -> Literal[
    "recovery_complete_node",
    "escalation_node",
]:
    """Continue only when human approval is explicitly true."""

    if state["human_approved"]:
        return "recovery_complete_node"

    return "escalation_node"


def route_after_tests(
    state: RecoveryState,
) -> Literal[
    "policy_risk_gateway",
    "repair_node",
    "escalation_node",
]:
    """
    Route according to validation outcome.

    retry_count is bounded at three autonomous retries.
    """

    exit_code = state["test_results"].get(
        "exit_code",
        -1,
    )

    if exit_code == 0:
        return "policy_risk_gateway"

    if state["retry_count"] < 3:
        return "repair_node"

    return "escalation_node"


def recovery_route(
    state: RecoveryState,
) -> str:
    if state["retry_count"] >= 3:
        return "escalation_node"

    score = float(
        state["explainable_risk"].get(
            "score",
            1.0,
        )
    )

    if score > 0.7:
        return "escalation_node"

    if (
        state["action_decision"] == "APPROVE"
        and not state["human_approved"]
    ):
        return "human_approval_node"

    if (
        state["test_results"].get(
            "exit_code",
            1,
        ) == 0
        and state["current_patch_diff"]
    ):
        return "pr_creator_node"

    return "repair_node"
