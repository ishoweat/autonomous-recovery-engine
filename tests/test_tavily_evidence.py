from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch
import pytest

from backend.services.tavily_evidence import (
    build_query,
    build_refined_query,
    _calculate_confidence,
    gather_evidence,
    _TAVILY_CACHE,
)
from backend.orchestration.risk import calculate_patch_risk
from backend.integrations.github_pr import build_recovery_pr_body


# ── 1. Unit Test: build_query output for sample errors ────────────────────────

def test_build_query_output_for_sample_errors():
    # Case A: String error with file path
    q1 = build_query(
        error="ZeroDivisionError: division by zero",
        file_path="backend/services/calculator.py",
    )
    assert "ZeroDivisionError: division by zero" in q1
    assert "calculator.py" in q1
    assert len(q1) <= 195

    # Case B: Dictionary error payload
    q2 = build_query(
        error={
            "errorMessage": "TypeError: Cannot read properties of undefined (reading 'stock')",
            "filePath": "src/inventoryService.js",
        }
    )
    assert "TypeError: Cannot read properties of undefined" in q2
    assert "inventoryService.js" in q2
    assert len(q2) <= 195

    # Case C: Context with library hint
    q3 = build_query(
        error="ValidationError: 1 validation error for RemediateRequest",
        file_path="backend/api/remediate.py",
        stack_trace="File pydantic/main.py, line 341 in pydantic 2.5",
    )
    assert "ValidationError" in q3
    assert "pydantic" in q3
    assert len(q3) <= 195

    # Case D: Refined query generation
    refined = build_refined_query(q1)
    assert "solution fix patch" in refined or "fix" in refined
    assert "in calculator.py" not in refined


# ── 2. Unit Test: Confidence Levels (high / medium / low / none) ─────────────

def test_confidence_levels_high_medium_low_none():
    # NONE: No sources
    assert _calculate_confidence([]) == "none"

    # LOW: 1 weak source (score < 0.70, not official docs)
    weak_sources = [
        {"domain": "randomforum.org", "score": 0.45, "title": "Random Forum Post"}
    ]
    assert _calculate_confidence(weak_sources) == "low"

    # MEDIUM: 1 strong source (score >= 0.70)
    medium_sources_score = [
        {"domain": "github.com", "score": 0.75, "title": "GitHub Issue 102"}
    ]
    assert _calculate_confidence(medium_sources_score) == "medium"

    # MEDIUM: Official docs domain even with lower score
    medium_sources_docs = [
        {"domain": "docs.python.org", "score": 0.55, "title": "Python Docs"}
    ]
    assert _calculate_confidence(medium_sources_docs) == "medium"

    # HIGH: 2+ independent domains with score >= 0.50
    high_sources = [
        {"domain": "github.com", "score": 0.65, "title": "GitHub Fix"},
        {"domain": "stackoverflow.com", "score": 0.72, "title": "SO Solution"},
    ]
    assert _calculate_confidence(high_sources) == "high"


# ── 3. Unit Test: Risk Gate Changes with Confidence ───────────────────────────

def test_risk_gate_changes_with_confidence():
    patch_diff = """--- a/service.py
+++ b/service.py
@@ -10,1 +10,2 @@
- return a / b
+ if b == 0: return 0
+ return a / b
"""
    files = ["service.py"]

    # HIGH confidence: bonus applied (-0.15), risk allows automated recovery
    risk_high = calculate_patch_risk(
        files=files,
        patch_diff=patch_diff,
        evidence_confidence="high",
    )
    assert risk_high["decision"] == "ALLOW"
    assert risk_high["score"] < 0.30
    assert any(
        c["factor"] == "external_evidence" and c["contribution"] == 0.05
        for c in risk_high["breakdown"]
    )

    # MEDIUM confidence: standard external evidence factor
    risk_med = calculate_patch_risk(
        files=files,
        patch_diff=patch_diff,
        evidence_confidence="medium",
    )
    assert any(
        c["factor"] == "external_evidence" and c["contribution"] == 0.15
        for c in risk_med["breakdown"]
    )

    # LOW confidence: risk elevated to at least 0.45, decision is APPROVE (blocks auto-merge)
    risk_low = calculate_patch_risk(
        files=files,
        patch_diff=patch_diff,
        evidence_confidence="low",
    )
    assert risk_low["decision"] in ("APPROVE", "BLOCK")
    assert risk_low["score"] >= 0.45

    # NONE confidence: risk elevated to at least 0.45, decision requires human approval
    risk_none = calculate_patch_risk(
        files=files,
        patch_diff=patch_diff,
        evidence_confidence="none",
    )
    assert risk_none["decision"] in ("APPROVE", "BLOCK")
    assert risk_none["score"] >= 0.45


# ── 4. Unit Test: PR Body Sources Section & "no evidence" Variant ─────────────

def test_pr_body_sources_section_and_no_evidence_variant():
    sample_root_cause = {"summary": "ZeroDivisionError due to empty sequence"}
    sample_risk = {"score": 0.25, "decision": "ALLOW", "breakdown": ["file_criticality: 0.10"]}
    sample_tests = {
        "exit_code": 0,
        "before_test": {"stdout": "FAILED test_average - ZeroDivisionError"},
        "after_test": {"stdout": "PASSED test_average in 0.02s"},
    }
    sample_diff = "+ if not numbers: return 0.0"

    # Variant A: Valid evidence present
    evidence_payload = {
        "confidence": "high",
        "sources": [
            {
                "id": 1,
                "title": "Python Division by Zero Guard",
                "url": "https://stackoverflow.com/questions/12345",
                "snippet": "Always check whether sequence is non-empty before computing average.",
                "support": "divisor zero guard validation",
            },
            {
                "id": 2,
                "title": "ZeroDivisionError Docs",
                "url": "https://docs.python.org/3/library/exceptions.html",
                "snippet": "Raised when the second argument of a division is zero.",
                "support": "standard exception handling",
            },
        ],
    }

    body_with_sources = build_recovery_pr_body(
        incident_id="rem-test-sources-1",
        root_cause=sample_root_cause,
        risk=sample_risk,
        test_results=sample_tests,
        patch_diff=sample_diff,
        evidence=evidence_payload,
    )

    assert "### Sources" in body_with_sources
    assert "- [1] [Python Division by Zero Guard](https://stackoverflow.com/questions/12345)" in body_with_sources
    assert "(Supports: divisor zero guard validation)" in body_with_sources
    assert "- [2] [ZeroDivisionError Docs](https://docs.python.org/3/library/exceptions.html)" in body_with_sources

    # Variant B: "no evidence" variant (evidence is None)
    body_no_evidence_none = build_recovery_pr_body(
        incident_id="rem-test-sources-2",
        root_cause=sample_root_cause,
        risk=sample_risk,
        test_results=sample_tests,
        patch_diff=sample_diff,
        evidence=None,
    )
    assert "### Sources\n\nNo external evidence found." in body_no_evidence_none

    # Variant C: "no evidence" variant (confidence == "none")
    body_no_evidence_conf_none = build_recovery_pr_body(
        incident_id="rem-test-sources-3",
        root_cause=sample_root_cause,
        risk=sample_risk,
        test_results=sample_tests,
        patch_diff=sample_diff,
        evidence={"confidence": "none", "sources": []},
    )
    assert "### Sources\n\nNo external evidence found." in body_no_evidence_conf_none


# ── 5. Unit Test: Mocked Tavily Search & Fallback Pipeline ───────────────────

@pytest.mark.asyncio
async def test_gather_evidence_with_mocked_tavily_client(monkeypatch):
    _TAVILY_CACHE.clear()
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key-mock-12345")

    mock_client_instance = MagicMock()
    mock_client_instance.search.return_value = {
        "results": [
            {
                "url": "https://github.com/fastapi/fastapi/issues/450",
                "title": "FastAPI Validation Error Guide",
                "content": "Ensure schema models specify optional fields correctly.",
                "score": 0.82,
            },
            {
                "url": "https://docs.pydantic.dev/latest/errors/",
                "title": "Pydantic Error Handling Documentation",
                "content": "Pydantic raised ValidationError when required keys are missing.",
                "score": 0.74,
            },
        ]
    }
    mock_client_instance.extract.return_value = {
        "results": [
            {
                "url": "https://github.com/fastapi/fastapi/issues/450",
                "raw_content": "Full extracted guide on FastAPI error resolution.",
            }
        ]
    }

    class MockTavilyModule:
        def TavilyClient(self, api_key):
            return mock_client_instance

    import sys
    monkeypatch.setitem(sys.modules, "tavily", MockTavilyModule())

    res = await gather_evidence(
        error="ValidationError: missing user_id field",
        file_path="backend/api/auth.py",
        stack_trace="in pydantic validator",
        incident_id="inc-mock-test",
    )

    assert len(res["sources"]) == 2
    assert res["confidence"] == "high"
    assert "github.com" in [s["domain"] for s in res["sources"]]
    assert "Cross-referenced 2 source(s) with high confidence" in res["why_fix"]
    assert "searched" in res["loop_trail"]


# ── 6. Unit Test: Failure Paths (Missing Key, Timeout, Refined Search) ────────

@pytest.mark.asyncio
async def test_gather_evidence_failure_paths_missing_key(monkeypatch):
    _TAVILY_CACHE.clear()
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    res = await gather_evidence(
        error="KeyError: 'token'",
        file_path="service.py",
    )
    assert res["confidence"] == "none"
    assert len(res["sources"]) == 0
    assert "no_api_key" in res["loop_trail"]
    assert "No external evidence found (TAVILY_API_KEY missing)" in res["why_fix"]


@pytest.mark.asyncio
async def test_gather_evidence_failure_paths_timeout(monkeypatch):
    _TAVILY_CACHE.clear()
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key-mock")

    async def mock_timeout_search(*args, **kwargs):
        raise asyncio.TimeoutError("Tavily search timed out")

    mock_client_instance = MagicMock()
    mock_client_instance.search.side_effect = asyncio.TimeoutError("Timeout")

    class MockTavilyModule:
        def TavilyClient(self, api_key):
            return mock_client_instance

    import sys
    monkeypatch.setitem(sys.modules, "tavily", MockTavilyModule())

    res = await gather_evidence(
        error="TimeoutError: test timeout",
        file_path="service.py",
    )
    assert res["confidence"] == "none"
    assert len(res["sources"]) == 0
    assert "failed" in res["loop_trail"]


@pytest.mark.asyncio
async def test_gather_evidence_empty_results_triggers_refined_search(monkeypatch):
    _TAVILY_CACHE.clear()
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key-mock")

    searches_called = []

    def mock_search(query, **kwargs):
        searches_called.append(query)
        if len(searches_called) == 1:
            # First search returns empty results
            return {"results": []}
        # Refined search returns fallback result or empty
        return {"results": []}

    mock_client_instance = MagicMock()
    mock_client_instance.search.side_effect = mock_search

    class MockTavilyModule:
        def TavilyClient(self, api_key):
            return mock_client_instance

    import sys
    monkeypatch.setitem(sys.modules, "tavily", MockTavilyModule())

    res = await gather_evidence(
        error="UnknownInternalCustomError: obscure error in inventory.js",
        file_path="src/inventory.js",
    )

    # Verifies refined search ran once
    assert len(searches_called) == 2
    assert "insufficient" in res["loop_trail"]
    assert "refined query" in res["loop_trail"]
    assert len(res["queries"]) == 2
    assert res["confidence"] == "none"

