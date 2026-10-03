import asyncio
import pytest
from backend.config import get_settings
from backend.llm.nebius import create_nebius_client, NebiusLLMError, NebiusNemotron
from backend.orchestration.prompts import SYSTEM_PROMPT, TRIAGE_PROMPT, ROOT_CAUSE_PROMPT, REPAIR_PROMPT
from backend.orchestration.state import RecoveryState
from backend.orchestration.nodes import triage_node, root_cause_node, repair_node
from backend.api.remediate import remediate_code, RemediateRequest


@pytest.mark.asyncio
async def test_nebius_configuration_and_credentials():
    """Verify API key is loaded and model is standardized."""
    settings = get_settings()
    assert settings.nebius_api_key, "NEBIUS_API_KEY must be configured"
    assert settings.nebius_model == "nvidia/Nemotron-3_5-Lightning", f"Expected nvidia/Nemotron-3_5-Lightning, got {settings.nebius_model}"
    assert "tokenfactory.nebius.com" in settings.nebius_base_url


@pytest.mark.asyncio
async def test_real_nemotron_live_completion():
    """Verify live inference against Nebius Token Factory."""
    client = create_nebius_client()
    try:
        response = await client.complete(
            system_prompt="You are a recovery engineer.",
            user_prompt="Respond with the exact word: RECOVERY_VERIFIED",
            max_tokens=128,
        )
        assert len(response) > 0

        # Verify telemetry
        telemetry = client.last_telemetry
        assert telemetry["provider"] == "Nebius Token Factory"
        assert telemetry["model"] == "nvidia/Nemotron-3_5-Lightning"
        assert telemetry["success"] is True
        assert telemetry["status_code"] == 200
        assert telemetry["latency"] > 0
        assert telemetry["request_id"] is not None
        assert "token_usage" in telemetry
        assert telemetry["inference_status"] == "RECEIVED"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_real_nemotron_structured_json():
    """Verify structured JSON completion from Nemotron."""
    client = create_nebius_client()
    try:
        json_resp = await client.complete_json(
            system_prompt="You are a diagnostics system. Return strict JSON with keys: status, engine, ready.",
            user_prompt="Diagnose system status.",
            max_tokens=1024,
        )
        assert isinstance(json_resp, dict)
        assert "status" in json_resp or "ready" in json_resp or len(json_resp) > 0
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_real_triage_inference():
    """Verify triage_node performs real Nemotron inference."""
    client = create_nebius_client()
    try:
        state: RecoveryState = {
            "incident_id": "test-triage-nemotron-001",
            "is_mock_mode": False,
            "retry_count": 0,
            "repository_full_name": "Sahil707-pop/third-ai-testing",
            "failure_file": "calculator.py",
            "failure_line": 5,
            "error_message": "ZeroDivisionError: division by zero in calculate_average",
            "stack_trace": "File calculator.py, line 5, in calculate_average: return total / len(numbers)\nZeroDivisionError: division by zero",
            "commit_sha": "c8a1f72",
            "github_payload": {
                "workflow_run": {"name": "pytest CI", "head_sha": "c8a1f72"},
                "repository": {"full_name": "Sahil707-pop/third-ai-testing"},
                "error": "ZeroDivisionError: division by zero",
            },
            "source_branch": "main",
            "default_branch": "main",
            "source_files": {"calculator.py": "def calculate_average(numbers):\n    total = sum(numbers)\n    return total / len(numbers)\n"},
            "triage_context": "",
            "root_cause_analysis": {},
            "explainable_risk": {},
            "action_decision": "ALLOW",
            "human_approved": None,
            "current_patch_diff": "",
            "test_results": {},
            "pr_url": "",
            "similar_past_cases": [],
            "learning_confidence_boost": 0.0,
            "patch_explanation": "",
            "generated_test_code": "",
            "is_shadow_mode": False,
            "polyglot_language": "python",
        }

        triage_res = await triage_node(state, llm=client)
        assert "triage_context" in triage_res
        assert len(triage_res["triage_context"]) > 10
        assert client.last_telemetry["success"] is True
        assert client.last_telemetry["model"] == "nvidia/Nemotron-3_5-Lightning"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_real_root_cause_inference():
    """Verify root_cause_node performs real Nemotron inference."""
    client = create_nebius_client()
    try:
        state: RecoveryState = {
            "incident_id": "test-rootcause-nemotron-001",
            "is_mock_mode": False,
            "retry_count": 0,
            "repository_full_name": "Sahil707-pop/third-ai-testing",
            "failure_file": "calculator.py",
            "failure_line": 5,
            "error_message": "ZeroDivisionError: division by zero",
            "stack_trace": "File calculator.py, line 5: return total / len(numbers)",
            "commit_sha": "c8a1f72",
            "triage_context": "Division by zero in calculate_average when numbers list is empty",
            "github_payload": {"error": "ZeroDivisionError"},
            "source_branch": "main",
            "default_branch": "main",
            "source_files": {"calculator.py": "def calculate_average(numbers):\n    total = sum(numbers)\n    return total / len(numbers)\n"},
            "root_cause_analysis": {},
            "explainable_risk": {},
            "action_decision": "ALLOW",
            "human_approved": None,
            "current_patch_diff": "",
            "test_results": {},
            "pr_url": "",
            "similar_past_cases": [],
            "learning_confidence_boost": 0.0,
            "patch_explanation": "",
            "generated_test_code": "",
            "is_shadow_mode": False,
            "polyglot_language": "python",
        }

        rc_res = await root_cause_node(state, llm=client)
        assert "root_cause_analysis" in rc_res
        rca = rc_res["root_cause_analysis"]
        assert "root_cause" in rca or "summary" in rca
        assert client.last_telemetry["success"] is True
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_real_repair_patch_generation():
    """Verify repair_node performs real Nemotron inference to generate patch."""
    client = create_nebius_client()
    try:
        state: RecoveryState = {
            "incident_id": "test-repair-nemotron-001",
            "is_mock_mode": False,
            "retry_count": 0,
            "repository_full_name": "Sahil707-pop/third-ai-testing",
            "failure_file": "calculator.py",
            "failure_line": 5,
            "error_message": "ZeroDivisionError: division by zero",
            "stack_trace": "File calculator.py, line 5: return total / len(numbers)",
            "commit_sha": "c8a1f72",
            "triage_context": "calculate_average crashes when passed empty list []",
            "root_cause_analysis": {
                "affected_file": "calculator.py",
                "error_type": "ZeroDivisionError",
                "root_cause": "calculate_average does not check if numbers is empty before dividing by len(numbers)",
            },
            "github_payload": {},
            "source_branch": "main",
            "default_branch": "main",
            "source_files": {"calculator.py": "def calculate_average(numbers):\n    \"\"\"Calculate average of numbers.\"\"\"\n    total = sum(numbers)\n    return total / len(numbers)\n"},
            "explainable_risk": {},
            "action_decision": "ALLOW",
            "human_approved": None,
            "current_patch_diff": "",
            "test_results": {},
            "pr_url": "",
            "similar_past_cases": [],
            "learning_confidence_boost": 0.0,
            "patch_explanation": "",
            "generated_test_code": "",
            "is_shadow_mode": False,
            "polyglot_language": "python",
        }

        rep_res = await repair_node(state, llm=client)
        assert "current_patch_diff" in rep_res
        patch = rep_res["current_patch_diff"]
        assert len(patch.strip()) > 0
        assert "patch_explanation" in rep_res
        assert len(rep_res["patch_explanation"]) > 0
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_real_remediate_endpoint():
    """Verify /api/remediate endpoint runs real Nemotron inference with full telemetry."""
    req = RemediateRequest(
        repoUrl="https://github.com/Sahil707-pop/third-ai-testing",
        filePath="calculator.py",
        fileContent="def calculate_average(numbers):\n    \"\"\"Calculate average of numbers.\"\"\"\n    total = sum(numbers)\n    return total / len(numbers)\n",
        errorMessage="ZeroDivisionError: division by zero",
        stackTrace="File calculator.py, line 4, in calculate_average: return total / len(numbers)\nZeroDivisionError: division by zero",
    )
    res = await remediate_code(req)
    assert res.incidentId.startswith("rem-")
    assert res.fixedCode != req.fileContent
    assert len(res.diff) > 0
    assert res.inference is not None
    assert res.inference.provider == "Nebius Token Factory"
    assert res.inference.model == "nvidia/Nemotron-3_5-Lightning"
    assert res.inference.success is True
    assert res.inference.latency > 0
    assert res.inference.inference_status == "RECEIVED"
    assert res.testResults["tests_passed"] is True


@pytest.mark.asyncio
async def test_invalid_api_key_fails_visibly_no_silent_fallback():
    """Verify invalid Nebius API key produces a visible failure state and never silent fallback."""
    bad_client = NebiusNemotron(
        api_key="invalid_bad_key_12345",
        base_url="https://api.tokenfactory.nebius.com/v1",
        model="nvidia/Nemotron-3_5-Lightning",
        temperature=0.1,
        max_tokens=256,
        timeout_seconds=10.0,
    )
    try:
        with pytest.raises(NebiusLLMError) as exc_info:
            await bad_client.complete(system_prompt="Test", user_prompt="Test")
        assert "Nebius" in str(exc_info.value) or "401" in str(exc_info.value) or "HTTP" in str(exc_info.value)
        assert bad_client.last_telemetry["success"] is False
        assert bad_client.last_telemetry["inference_status"] == "ERROR"
    finally:
        await bad_client.close()
