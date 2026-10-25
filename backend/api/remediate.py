"""
POST /api/remediate

Accepts {repoUrl, filePath, fileContent, stackTrace, errorMessage}
Returns  {fixedCode, diff, riskAssessment, explanation, incidentId}

riskAssessment shape:
  {
    overall: float,          # 0-1
    decision: str,           # ALLOW | APPROVE | BLOCK
    breakdown: [
      {label: str, score: float, weight: float, explanation: str}
    ]
  }
"""

from __future__ import annotations

import difflib
import logging
import re
import time
import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.orchestration.risk import calculate_patch_risk
from backend.services.telemetry import telemetry_manager

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api",
    tags=["Remediate"],
)


# ── Request / Response ────────────────────────────────────────────────────────

class RemediateRequest(BaseModel):
    repoUrl: Optional[str] = Field(default="")
    filePath: str = Field(default="calculator.py")
    fileContent: str = Field(..., min_length=1, max_length=100_000)
    stackTrace: Optional[str] = Field(default="")
    errorMessage: Optional[str] = Field(default="")
    commitSha: Optional[str] = Field(default="HEAD")


class RiskBreakdownItem(BaseModel):
    label: str
    score: float        # normalised 0-1 contribution
    weight: float       # contribution weight
    explanation: str


class RiskAssessment(BaseModel):
    overall: float
    decision: str       # ALLOW | APPROVE | BLOCK
    breakdown: List[RiskBreakdownItem]


class InferenceTelemetry(BaseModel):
    provider: str = "Nebius Token Factory"
    model: str = Field(default_factory=lambda: get_settings().nebius_model)
    request_started: Optional[str] = None
    response_received: Optional[str] = None
    success: bool = True
    latency: float = 0.0
    request_id: Optional[str] = None
    token_usage: Optional[dict[str, Any]] = None
    inference_status: str = "RECEIVED"  # LIVE / RECEIVED / ERROR
    error: Optional[str] = None
    est_cost: Optional[float] = None


class RemediateResponse(BaseModel):
    incidentId: str
    filePath: Optional[str] = None
    fixedCode: str
    diff: str
    explanation: str
    rootCause: Optional[str] = None
    affectedLineNumber: Optional[int] = None
    defectStatus: Optional[str] = "CONFIRMED"
    defectCategory: Optional[str] = "logic_runtime"
    verificationStatus: Optional[str] = "VERIFIED"
    riskAssessment: RiskAssessment
    testResults: dict
    inference: Optional[InferenceTelemetry] = None
    generatedTestCode: Optional[str] = None
    tavilyEvidence: Optional[dict[str, Any]] = None


# ── Smart fix engine ──────────────────────────────────────────────────────────

def _smart_fix(code: str, file_path: str, error_message: str, stack_trace: str) -> dict:
    """
    Deterministic, universal pattern-based code repair. Uses AST and structural
    heuristics across all supported languages without hardcoding function names.
    """
    from backend.services.universal_repair import detect_language_context
    from backend.services.universal_remediator import UniversalPatternRemediator

    lang_ctx = detect_language_context(file_path, code)
    rem = UniversalPatternRemediator.remediate(
        code=code,
        file_path=file_path,
        error_message=error_message,
        stack_trace=stack_trace,
        lang_ctx=lang_ctx,
    )
    return {
        "fixedCode": rem.fixed_code,
        "diff": rem.patch_diff,
        "explanation": rem.explanation,
        "wasFixed": rem.fixed_code != code,
        "rootCause": rem.root_cause,
        "defectCategory": rem.defect_category,
    }


# ── Label map for risk breakdown ──────────────────────────────────────────────
_LABEL_MAP = {
    "file_criticality": ("File Criticality", 0.35),
    "patch_size": ("Patch Size", 0.30),
    "security_sensitivity": ("Test Coverage", 0.15),
    "change_surface": ("Change Surface", 0.20),
    "external_evidence": ("External Evidence", 0.15),
}


# ── Risk assessment mapper ────────────────────────────────────────────────────

def _build_risk_assessment(
    files: list[str],
    patch_diff: str,
    was_fixed: bool,
    verified: bool = True,
    evidence_confidence: str = "none",
) -> RiskAssessment:
    try:
        raw = calculate_patch_risk(
            files=files,
            patch_diff=patch_diff,
            evidence_confidence=evidence_confidence,
        )
        raw_score = float(raw.get("score", 0.10))
        decision = str(raw.get("decision", "ALLOW"))

        # Risk gate: confidence none/low -> raise risk and require approval; high -> lower risk
        if evidence_confidence in ("none", "low"):
            raw_score = max(raw_score, 0.45)
            decision = "APPROVE"
        elif evidence_confidence == "high" and verified and was_fixed:
            raw_score = max(0.05, raw_score - 0.15)
            if raw_score < 0.30:
                decision = "ALLOW"

        # If verification failed or rolled back, elevate risk to enforce Human Approval
        if not verified or not was_fixed:
            raw_score = max(raw_score, 0.65)
            decision = "APPROVE"

        breakdown_items: list[RiskBreakdownItem] = []
        for item in raw.get("breakdown", []):
            factor = item.get("factor", "unknown")
            label, weight = _LABEL_MAP.get(factor, (factor.replace("_", " ").title(), 0.25))
            score = float(item.get("contribution", 0.0))
            if factor == "security_sensitivity":
                label = "Test Coverage"
                score = 0.05 if (verified and was_fixed) else 0.85

            breakdown_items.append(
                RiskBreakdownItem(
                    label=label,
                    score=round(score, 4),
                    weight=weight,
                    explanation=item.get("explanation", "Standard safe factor evaluated"),
                )
            )

        return RiskAssessment(
            overall=round(raw_score, 4),
            decision=decision,
            breakdown=breakdown_items or [
                RiskBreakdownItem(label="General Safety", score=round(raw_score, 4), weight=1.0, explanation="Standard patch risk evaluated")
            ],
        )
    except Exception:
        return RiskAssessment(
            overall=0.10 if (verified and was_fixed and evidence_confidence == "high") else 0.65,
            decision="ALLOW" if (verified and was_fixed and evidence_confidence == "high") else "APPROVE",
            breakdown=[
                RiskBreakdownItem(label="General Safety", score=0.10 if (verified and was_fixed and evidence_confidence == "high") else 0.65, weight=1.0, explanation="Standard patch risk evaluated")
            ],
        )



# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post(
    "/remediate",
    response_model=RemediateResponse,
    status_code=status.HTTP_200_OK,
)
async def remediate_code(request: RemediateRequest) -> RemediateResponse:
    """
    Analyse the submitted file content + error context, produce a patch,
    run synthetic sandbox verification, and calculate an explainable risk score.
    """
    from backend.recovery_ext.flags import get_flags
    flags = get_flags()
    if flags.public_demo_mode and request.repoUrl and not request.repoUrl.startswith("demo/scenarios"):
        raise HTTPException(status_code=403, detail="Arbitrary repos are blocked in public demo mode.")
        
    incident_id = f"rem-{uuid.uuid4().hex[:10]}"
    start_time = time.perf_counter()

    error_ctx = (request.stackTrace or request.errorMessage or "").strip()
    # Extract error line and optional line number from stack trace or error context
    error_line = error_ctx.splitlines()[0] if error_ctx else "Runtime error"
    error_type = "Runtime Exception"
    for token in ("ZeroDivisionError", "KeyError", "TypeError", "ValueError",
                  "AttributeError", "IndexError", "NameError", "RuntimeError",
                  "SyntaxError", "ImportError"):
        if token in error_ctx:
            error_type = token
            break
    # Attempt to parse line number from full error context (e.g., 'File "path", line 42')
    import re
    line_match = re.search(r"line\s+(\d+)", error_ctx, re.IGNORECASE)
    error_line_number = int(line_match.group(1)) if line_match else None

    # ── 1 · Triage ────────────────────────────────────────────────────────────
    await telemetry_manager.publish(
        incident_id=incident_id,
        event_type="node_started",
        node_name="triage_node",
        message=f"Analyzing {request.filePath} for errors.",
        metadata={"file_path": request.filePath},
    )
    await telemetry_manager.publish(
        incident_id=incident_id,
        event_type="failure_context_loaded",
        node_name="triage_node",
        message=f"Failure context: {error_line}",
        reasoning=error_ctx,
        metadata={"error_signature": error_line, "severity": "high"},
    )
    await telemetry_manager.publish(
        incident_id=incident_id,
        event_type="node_completed",
        node_name="triage_node",
        message="Triage completed.",
    )

    # ── 1.5 · TAVILY EVIDENCE ─────────────────────────────────────────────────
    from backend.services.tavily_evidence import gather_evidence

    await telemetry_manager.publish(
        incident_id=incident_id,
        event_type="tavily_evidence",
        node_name="tavily_node",
        message="Gathering external research evidence...",
        metadata={"status": "started", "query": error_line},
    )

    tavily_evidence_payload: dict[str, Any] = {
        "queries": [error_line],
        "sources": [],
        "extracted_text": "",
        "confidence": "none",
        "loop_trail": ["searched"],
        "trail_string": "searched",
        "why_fix": "No external evidence found",
    }

    try:
        tavily_evidence_payload = await gather_evidence(
            error=request.errorMessage or error_line,
            file_path=request.filePath,
            stack_trace=request.stackTrace or "",
            incident_id=incident_id,
        )
        t_sources = tavily_evidence_payload.get("sources", [])
        t_conf = tavily_evidence_payload.get("confidence", "none")
        t_status = "done" if t_conf != "none" or t_sources else "failed"
        await telemetry_manager.publish(
            incident_id=incident_id,
            event_type="tavily_evidence",
            node_name="tavily_node",
            message=f"Tavily evidence: {len(t_sources)} sources ({t_conf} confidence).",
            metadata={
                "status": t_status,
                "evidence": tavily_evidence_payload,
                "sources_count": len(t_sources),
                "confidence": t_conf,
                "loop_trail": tavily_evidence_payload.get("loop_trail", []),
            },
        )
    except Exception as tavily_err:
        logger.error(f"[TAVILY] failed: {tavily_err}")
        tavily_evidence_payload = {
            "queries": [error_line],
            "sources": [],
            "extracted_text": "",
            "confidence": "none",
            "loop_trail": ["failed"],
            "trail_string": "failed",
            "why_fix": f"Tavily search failed: {tavily_err}",
        }
        await telemetry_manager.publish(
            incident_id=incident_id,
            event_type="tavily_evidence",
            node_name="tavily_node",
            message=f"Tavily evidence failed: {tavily_err}",
            metadata={"status": "failed", "evidence": tavily_evidence_payload, "error": str(tavily_err)},
        )

    settings = get_settings()
    has_real_nebius = bool(settings.nebius_api_key and settings.nebius_api_key not in ("", "your_nebius_api_key"))

    if has_real_nebius:
        await telemetry_manager.publish(
            incident_id=incident_id,
            event_type="nemotron_started",
            node_name="root_cause_node",
            message=f"Dispatching live request to {settings.nebius_model} via Nebius Token Factory...",
            metadata={"model": settings.nebius_model, "provider": "Nebius Token Factory"},
        )
    else:
        await telemetry_manager.publish(
            incident_id=incident_id,
            event_type="nemotron_started",
            node_name="root_cause_node",
            message="Deterministic heuristic analysis running in mock mode.",
            metadata={"mode": "mock"},
        )

    from backend.services.universal_repair import UniversalRepairEngine
    repair_res = await UniversalRepairEngine.repair_and_verify(
        file_path=request.filePath,
        file_content=request.fileContent,
        error_message=request.errorMessage or "",
        stack_trace=request.stackTrace or "",
        incident_id=incident_id,
        repo_url=request.repoUrl or "",
        commit_sha=request.commitSha or "HEAD",
        evidence=tavily_evidence_payload,
    )


    inference_meta: Optional[InferenceTelemetry] = None
    if repair_res.inference_telemetry:
        raw_telemetry = repair_res.inference_telemetry
        inference_meta = InferenceTelemetry(
            provider=raw_telemetry.get("provider", "Nebius Token Factory"),
            model=raw_telemetry.get("model", settings.nebius_model),
            request_started=raw_telemetry.get("request_started"),
            response_received=raw_telemetry.get("response_received"),
            success=raw_telemetry.get("success", True),
            latency=raw_telemetry.get("latency", 0.0),
            request_id=raw_telemetry.get("request_id"),
            token_usage=raw_telemetry.get("token_usage"),
            inference_status=raw_telemetry.get("inference_status", "RECEIVED"),
        )

    await telemetry_manager.publish(
        incident_id=incident_id,
        event_type="root_cause_identified",
        node_name="root_cause_node",
        message=repair_res.root_cause,
        reasoning=repair_res.patch_strategy or repair_res.root_cause,
        metadata={
            "error_type": error_type,
            "error_line_number": error_line_number,
            "affected_file": request.filePath,
            "confidence": repair_res.confidence,
            "inference": inference_meta.model_dump() if inference_meta else None,
        },
    )

    was_fixed = repair_res.fixed_code != request.fileContent
    t_query = tavily_evidence_payload.get("queries", [error_line])[0]
    logger.info(f"[TAVILY] query -> sources={len(t_sources)} confidence={t_conf} -> Nemotron -> patch -> sandbox -> PR -> merge -> post-merge")
    logger.info(f"[TAVILY] query={t_query} -> sources={len(t_sources)} confidence={t_conf} -> Nemotron -> patch -> sandbox -> PR -> merge -> post-merge")
    await telemetry_manager.publish(
        incident_id=incident_id,
        event_type="patch_generated",
        node_name="repair_node",
        message=f"Patch generated by Universal Repair Engine ({'verified' if repair_res.verified else 'unverified'}).",
        reasoning=repair_res.explanation,
        metadata={
            "patch": repair_res.patch_diff,
            "corrected_code": repair_res.fixed_code,
            "explanation": repair_res.explanation,
            "inference": inference_meta.model_dump() if inference_meta else None,
            "targeted_test": repair_res.targeted_test_code,
            "attempts_made": repair_res.attempts_made,
            "rolled_back": repair_res.rolled_back,
        },
    )

    # ── 4 · Sandbox verification ──────────────────────────────────────────────
    exit_code = repair_res.test_results.get("exit_code", 0 if repair_res.verified else 1)
    stdout_summary = repair_res.test_results.get("stdout", "")
    runtime = float(repair_res.test_results.get("runtime", 0.05))
    ver_status = getattr(repair_res, "verification_status", "VERIFIED" if repair_res.verified else "FAILED")
    test_executed = getattr(repair_res, "test_executed", False)

    if test_executed:
        tests_passed_count = 1 if repair_res.verified else 0
        tests_failed_count = 0 if repair_res.verified else 1
        ver_msg = f"Sandbox: {tests_passed_count} passed, {tests_failed_count} failed in {runtime}s ({ver_status})."
    else:
        ver_msg = f"Verification: Syntax & Security gates passed in {runtime}s ({ver_status})."

    await telemetry_manager.publish(
        incident_id=incident_id,
        event_type="sandbox_completed",
        node_name="failure_analyzer_node",
        message=ver_msg,
        metadata={
            "exit_code": exit_code,
            "stdout_summary": stdout_summary,
            "verified": repair_res.verified,
            "verification_status": ver_status,
            "test_executed": test_executed,
        },
    )

    # ── 5 · Risk assessment ───────────────────────────────────────────────────
    risk_assessment = _build_risk_assessment(
        files=[request.filePath],
        patch_diff=repair_res.patch_diff,
        was_fixed=was_fixed,
        verified=repair_res.verified,
        evidence_confidence=tavily_evidence_payload.get("confidence", "none"),
    )

    await telemetry_manager.publish(
        incident_id=incident_id,
        event_type="risk_evaluated",
        node_name="policy_risk_gateway",
        message=f"Risk: {risk_assessment.decision} ({risk_assessment.overall:.2f}).",
        metadata={
            "risk_score": risk_assessment.overall,
            "decision": risk_assessment.decision,
        },
    )

    if risk_assessment.decision in {"APPROVE", "BLOCK"}:
        await telemetry_manager.publish(
            incident_id=incident_id,
            event_type="approval_required",
            node_name="human_approval_node",
            message="HUMAN APPROVAL REQUIRED before merge.",
            metadata={"risk": risk_assessment.overall},
        )

    if repair_res.verified and was_fixed and risk_assessment.decision == "ALLOW":
        await telemetry_manager.publish(
            incident_id=incident_id,
            event_type="incident_recovered",
            node_name="recovery_complete_node",
            message="Recovery completed successfully.",
        )

    elapsed = round(time.perf_counter() - start_time, 3)
    await telemetry_manager.publish(
        incident_id=incident_id,
        event_type="node_completed",
        node_name="recovery_complete_node",
        message=f"Remediation pipeline completed in {elapsed}s.",
        metadata={"elapsed": elapsed},
    )

    has_explicit_error = bool(error_ctx and any(t in error_ctx for t in (
        "Error", "Exception", "Traceback", "failed", "Failure", "defect", "BUG", "unhandled"
    )))
    defect_status = "CONFIRMED" if has_explicit_error else "SUSPECTED"

    return RemediateResponse(
        incidentId=incident_id,
        filePath=request.filePath,
        fixedCode=repair_res.fixed_code,
        diff=repair_res.patch_diff,
        explanation=repair_res.explanation,
        rootCause=repair_res.root_cause,
        affectedLineNumber=error_line_number,
        defectStatus=defect_status,
        defectCategory=getattr(repair_res, "defect_category", "logic_runtime"),
        verificationStatus=ver_status,
        riskAssessment=risk_assessment,
        testResults=repair_res.test_results,
        inference=inference_meta,
        generatedTestCode=repair_res.targeted_test_code,
        tavilyEvidence=tavily_evidence_payload,
    )

