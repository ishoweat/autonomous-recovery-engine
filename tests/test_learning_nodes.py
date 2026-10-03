import pytest
from backend.orchestration.nodes import (
    root_cause_node,
    repair_node,
    recovery_complete_node,
)
from backend.orchestration.state_factory import create_initial_recovery_state
from backend.services.knowledge import record_learned_pattern, find_similar_patterns


@pytest.mark.asyncio
async def test_recovery_state_fields():
    state = create_initial_recovery_state(
        incident_id="test-learning-state-001",
        github_payload={"repository": {"full_name": "owner/repo"}},
        is_mock_mode=True,
        is_shadow_mode=True,
    )

    assert "similar_past_cases" in state
    assert "learning_confidence_boost" in state
    assert "patch_explanation" in state
    assert "generated_test_code" in state
    assert "is_shadow_mode" in state
    assert state["is_shadow_mode"] is True
    assert state["learning_confidence_boost"] == 0.0


@pytest.mark.asyncio
async def test_root_cause_node_with_knowledge_base_boost():
    # Pre-populate a learned pattern in the knowledge base
    pattern = await record_learned_pattern(
        error_type="KeyError",
        root_cause_summary="Missing key 'user_id' in payload",
        patch_pattern="payload.get('user_id')",
        confidence=0.95,
        repository="owner/repo",
        incident_id="prev-incident-001",
    )

    state = create_initial_recovery_state(
        incident_id="test-incident-recall-002",
        github_payload={"repository": {"full_name": "owner/repo"}},
        is_mock_mode=True,
    )
    state["triage_context"] = "High severity failure with KeyError in auth handler."

    result = await root_cause_node(state, llm=None)

    assert "root_cause_analysis" in result
    assert "similar_past_cases" in result
    assert "learning_confidence_boost" in result
    assert len(result["similar_past_cases"]) > 0
    assert result["learning_confidence_boost"] > 0.0
    assert result["root_cause_analysis"]["confidence"] >= 0.95


@pytest.mark.asyncio
async def test_repair_node_generates_explanation_and_test():
    state = create_initial_recovery_state(
        incident_id="test-incident-repair-003",
        github_payload={"repository": {"full_name": "owner/repo"}},
        is_mock_mode=True,
    )
    state["triage_context"] = "KeyError 'user_id' regression in auth.py"
    state["root_cause_analysis"] = {
        "error_type": "KeyError",
        "affected_file": "backend/api/auth.py",
        "root_cause": "Missing payload validation",
        "confidence": 0.98,
    }

    result = await repair_node(state, llm=None)

    assert "current_patch_diff" in result
    assert "patch_explanation" in result
    assert "generated_test_code" in result

    assert "Why I fixed it this way" in result["patch_explanation"]
    assert "def test_" in result["generated_test_code"]
    assert "pytest.raises" in result["generated_test_code"]
