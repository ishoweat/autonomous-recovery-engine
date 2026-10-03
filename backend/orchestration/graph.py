from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from backend.llm.nebius import NebiusNemotron
from backend.orchestration.nodes import (
    adversarial_resilience_node,
    escalation_node,
    failure_analyzer_node,
    human_approval_node,
    policy_risk_gateway,
    decision_router_node,
    recovery_complete_node,
    repair_node,
    root_cause_node,
    triage_node,
)
from backend.orchestration.retry import increment_retry_node
from backend.orchestration.routing import (
    route_after_approval,
    route_after_risk,
    route_after_tests,
)
from backend.orchestration.state import RecoveryState


def build_recovery_graph(
    *,
    checkpointer: BaseCheckpointSaver,
    llm: NebiusNemotron | None,
    fast_llm: NebiusNemotron | None = None,
):
    """
    Build and compile the Autonomous Recovery Engine graph.

    The same exact RecoveryState is shared by every node.
    """

    async def triage(state: RecoveryState) -> dict[str, Any]:
        return await triage_node(
            state,
            llm=fast_llm or llm,
        )

    async def root_cause(
        state: RecoveryState,
    ) -> dict[str, Any]:
        return await root_cause_node(
            state,
            llm=llm,
        )

    async def risk_gateway(
        state: RecoveryState,
    ) -> dict[str, Any]:
        return await policy_risk_gateway(
            state,
            llm=llm,
        )

    async def decision_router(
        state: RecoveryState,
    ) -> dict[str, Any]:
        return await decision_router_node(
            state,
            llm=llm,
        )

    async def approval(
        state: RecoveryState,
    ) -> dict[str, Any]:
        return await human_approval_node(
            state,
            llm=llm,
        )

    async def repair(
        state: RecoveryState,
    ) -> dict[str, Any]:
        return await repair_node(
            state,
            llm=llm,
        )

    async def adversarial(
        state: RecoveryState,
    ) -> dict[str, Any]:
        return await adversarial_resilience_node(
            state,
            llm=llm,
        )

    async def failure_analysis(
        state: RecoveryState,
    ) -> dict[str, Any]:
        return await failure_analyzer_node(
            state,
            llm=llm,
        )

    async def escalation(
        state: RecoveryState,
    ) -> dict[str, Any]:
        return await escalation_node(
            state,
            llm=llm,
        )

    async def complete(
        state: RecoveryState,
    ) -> dict[str, Any]:
        return await recovery_complete_node(
            state,
            llm=llm,
        )

    workflow = StateGraph(RecoveryState)

    workflow.add_node(
        "triage_node",
        triage,
    )

    workflow.add_node(
        "root_cause_node",
        root_cause,
    )

    workflow.add_node(
        "policy_risk_gateway",
        risk_gateway,
    )

    workflow.add_node(
        "decision_router",
        decision_router,
    )

    workflow.add_node(
        "human_approval_node",
        approval,
    )

    workflow.add_node(
        "repair_node",
        repair,
    )

    workflow.add_node(
        "adversarial_resilience_node",
        adversarial,
    )

    workflow.add_node(
        "failure_analyzer_node",
        failure_analysis,
    )

    workflow.add_node(
        "increment_retry_node",
        increment_retry_node,
    )

    workflow.add_node(
        "escalation_node",
        escalation,
    )

    workflow.add_node(
        "recovery_complete_node",
        complete,
    )

    workflow.add_edge(
        START,
        "triage_node",
    )

    workflow.add_edge(
        "triage_node",
        "root_cause_node",
    )

    workflow.add_edge(
        "root_cause_node",
        "repair_node",
    )

    workflow.add_edge(
        "repair_node",
        "adversarial_resilience_node",
    )

    workflow.add_edge(
        "adversarial_resilience_node",
        "failure_analyzer_node",
    )

    workflow.add_conditional_edges(
        "failure_analyzer_node",
        route_after_tests,
        {
            "policy_risk_gateway": (
                "policy_risk_gateway"
            ),
            "repair_node": "increment_retry_node",
            "escalation_node": "escalation_node",
        },
    )

    workflow.add_edge(
        "increment_retry_node",
        "repair_node",
    )
    
    workflow.add_edge(
        "policy_risk_gateway",
        "decision_router",
    )

    workflow.add_conditional_edges(
        "decision_router",
        route_after_risk,
        {
            "human_approval_node": "human_approval_node",
            "escalation_node": "escalation_node",
            "recovery_complete_node": "recovery_complete_node",
        },
    )

    workflow.add_conditional_edges(
        "human_approval_node",
        route_after_approval,
        {
            "recovery_complete_node": "recovery_complete_node",
            "escalation_node": "escalation_node",
        },
    )

    workflow.add_edge(
        "escalation_node",
        END,
    )

    workflow.add_edge(
        "recovery_complete_node",
        END,
    )

    return workflow.compile(
        checkpointer=checkpointer,
    )

