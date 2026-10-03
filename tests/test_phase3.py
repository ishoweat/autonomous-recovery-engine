import pytest
import pytest_asyncio
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from backend.orchestration.risk import calculate_patch_risk
from backend.orchestration.state import RecoveryState
from backend.orchestration.state_factory import create_initial_recovery_state
from backend.orchestration.graph import build_recovery_graph
from backend.orchestration.routing import route_after_risk, route_after_approval, route_after_tests


def test_deterministic_risk_gateway():
    # ALLOW path (< 0.3)
    res_allow = calculate_patch_risk(
        files=["backend/services/utils.py"],
        patch_diff=" + line of code"
    )
    assert res_allow["decision"] in ["ALLOW", "APPROVE"]
    assert res_allow["score"] < 0.70

    # APPROVE / High risk path for critical auth file (backend/api/auth.py)
    res_auth = calculate_patch_risk(
        files=["backend/api/auth.py"],
        patch_diff=" + user_id check"
    )
    assert res_auth["score"] >= 0.30
    assert "backend/api/auth.py" in res_auth["breakdown"][0]["explanation"]

    # BLOCK path (> 0.7) for many files + large diff
    res_block = calculate_patch_risk(
        files=["backend/api/auth.py", "backend/api/webhooks.py", "backend/db/models.py", "backend/config.py", "backend/services/other.py"],
        patch_diff="\n".join([f"+ line {i}" for i in range(30)])
    )
    assert res_block["score"] > 0.70
    assert res_block["decision"] == "BLOCK"


def test_routing_rules():
    state = create_initial_recovery_state(
        incident_id="inc-route-1",
        github_payload={},
        is_mock_mode=True
    )
    state["action_decision"] = "ALLOW"
    assert route_after_risk(state) in ("recovery_complete_node", "repair_node")

    state["action_decision"] = "APPROVE"
    assert route_after_risk(state) == "human_approval_node"

    state["action_decision"] = "BLOCK"
    assert route_after_risk(state) == "escalation_node"

    state["human_approved"] = True
    assert route_after_approval(state) in ("recovery_complete_node", "repair_node")
    state["human_approved"] = False
    assert route_after_approval(state) == "escalation_node"

    state["test_results"] = {"exit_code": 0}
    assert route_after_tests(state) in ("policy_risk_gateway", "recovery_complete_node")

    state["test_results"] = {"exit_code": 1}
    state["retry_count"] = 1
    assert route_after_tests(state) == "repair_node"

    state["retry_count"] = 3
    assert route_after_tests(state) == "escalation_node"


@pytest_asyncio.fixture
async def memory_graph():
    checkpointer = MemorySaver()
    graph = build_recovery_graph(checkpointer=checkpointer, llm=None)
    return graph


@pytest.mark.asyncio
async def test_mock_mode_graph_execution(memory_graph):
    state = create_initial_recovery_state(
        incident_id="inc-mock-test",
        github_payload={"repository": {"full_name": "acme/demo"}},
        is_mock_mode=True
    )
    config = {"configurable": {"thread_id": "inc-mock-test"}}

    result = await memory_graph.ainvoke(state, config=config)
    assert result["triage_context"] != ""
    assert result["root_cause_analysis"]["error_type"] == "KeyError"
    # Single-file critical patch scores 0.50 -> APPROVE or BLOCK
    assert result["action_decision"] in ("APPROVE", "BLOCK")
