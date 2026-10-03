import pytest
from backend.orchestration.routing import route_after_risk

def test_router_0_29():
    state = {"action_decision": "ALLOW"}
    result = route_after_risk(state)
    assert result == "recovery_complete_node"

def test_router_0_30():
    state = {"action_decision": "APPROVE"}
    result = route_after_risk(state)
    assert result == "human_approval_node"

def test_router_0_70():
    state = {"action_decision": "APPROVE"}
    result = route_after_risk(state)
    assert result == "human_approval_node"

def test_router_0_71():
    state = {"action_decision": "BLOCK"}
    result = route_after_risk(state)
    assert result == "escalation_node"
