"""
ARE Upgrade — v2 API Router
============================
Exposes the three ARE modules as standalone REST endpoints.

Mount in main.py with:
    from backend.api.v2 import router as v2_router
    application.include_router(v2_router)

Endpoints:
    POST /api/v2/adversarial/check   — run all 3 adversarial checks on any patch
    POST /api/v2/polyglot/fix        — generate a language-correct fix + test
    POST /api/v2/roi/record          — manually record a completed fix
    GET  /api/v2/roi/dashboard       — full ROI metrics (mirrors /api/v1/roi/dashboard)
    GET  /api/v2/roi/weekly-report   — markdown weekly report
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db.session import get_db
from backend.orchestration.adversarial import AdversarialResilienceLayer
from backend.orchestration.polyglot import PolyglotFixEngine
from backend.services.roi import (
    get_dashboard_data,
    get_recent_records,
    record_fix,
    weekly_report,
)

router = APIRouter(
    prefix="/api/v2",
    tags=["ARE Upgrades v2"],
)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _make_llm_or_none():
    """
    Return a live NebiusNemotron client when the API key is configured,
    otherwise return None so callers fall back to mock mode.
    """
    settings = get_settings()
    if not settings.nebius_api_key:
        return None
    from backend.llm.nebius import create_nebius_client
    return create_nebius_client()


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────


class AdversarialCheckRequest(BaseModel):
    patch_code: str = Field(
        ...,
        description="Source code of the generated patch to validate.",
    )
    patch_diff: str = Field(
        default="",
        description=(
            "Unified diff of the patch (used for supply-chain CVE extraction). "
            "Falls back to patch_code when omitted."
        ),
    )
    test_cmd: str = Field(
        default="pytest --tb=no -q",
        description="Shell command used to re-run tests during mutation testing.",
    )
    mock_mode: bool = Field(
        default=False,
        description=(
            "When true, returns a deterministic safe report without calling "
            "Nebius or running subprocesses.  Useful for CI smoke tests."
        ),
    )


class PolyglotFixRequest(BaseModel):
    failed_test_log: str = Field(
        ...,
        description="Full stdout + stderr from the failing test run.",
    )
    source_files: dict[str, str] = Field(
        ...,
        description="Map of {filename: file_content} for the affected source files.",
    )
    mock_mode: bool = Field(
        default=False,
        description=(
            "When true, returns a deterministic Python mock fix without calling "
            "Nebius.  Useful for CI smoke tests."
        ),
    )


class RecordFixRequest(BaseModel):
    fix_id: str = Field(
        ...,
        description="Unique identifier for this fix (use incident_id from RecoveryState).",
    )
    language: str = Field(
        default="python",
        description="Programming language of the fixed code.",
    )
    severity: str = Field(
        default="LOW",
        description="Severity of the incident: LOW, MEDIUM, or HIGH.",
    )
    mttr_before_min: float = Field(
        default=45.0,
        description="Minutes the failure was open before ARE resolved it.",
    )
    mttr_after_min: float = Field(
        default=0.5,
        description="Wall-clock minutes ARE spent on the fix.",
    )
    was_automated: bool = Field(
        default=True,
        description="True when no human approval was required.",
    )
    repository: str = Field(
        default="",
        description="Full repository name (e.g. org/repo).",
    )


# ─────────────────────────────────────────────────────────────────────────────
# OPTION 1 — Adversarial Check
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/adversarial/check",
    summary="Run all three adversarial checks on a patch",
)
async def adversarial_check(
    req: AdversarialCheckRequest,
) -> dict[str, Any]:
    """
    Runs the Adversarial Resilience Layer against the submitted patch:

    1. **Mutation Testing** — injects operator mutations and re-runs tests
    2. **Supply Chain CVE** — checks new imports against OSV.dev
    3. **Behavioral Replay** — Nemotron-70B static analysis for leaks / races

    Set `mock_mode=true` for instant deterministic responses in CI.
    """
    try:
        llm = None if req.mock_mode else _make_llm_or_none()
        effective_mock = req.mock_mode or (llm is None)

        layer = AdversarialResilienceLayer(
            patch_code=req.patch_code,
            patch_diff=req.patch_diff or req.patch_code,
            test_cmd=req.test_cmd,
            llm=llm,
            is_mock_mode=effective_mock,
        )
        report = await layer.run_all_checks()
        return report.as_dict()

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


# ─────────────────────────────────────────────────────────────────────────────
# OPTION 2 — Polyglot Fix
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/polyglot/fix",
    summary="Generate a language-correct fix and regression test",
)
async def polyglot_fix(
    req: PolyglotFixRequest,
) -> dict[str, Any]:
    """
    Runs the four-step Polyglot Fix Engine:

    1. **Language Detection** — extension-frequency heuristic
    2. **Semantic Root Cause** — Nemotron extracts the conceptual failure
    3. **Fix + Test Generation** — targeted patch in the detected language/framework
    4. **Multi-Audience Explanations** — devops / product / researcher variants

    Set `mock_mode=true` to receive a deterministic Python fixture without
    calling Nebius (useful for UI development and CI).
    """
    try:
        llm = None if req.mock_mode else _make_llm_or_none()
        effective_mock = req.mock_mode or (llm is None)

        engine = PolyglotFixEngine(
            failed_test_log=req.failed_test_log,
            source_files=req.source_files,
            llm=llm,
            is_mock_mode=effective_mock,
        )
        result = await engine.generate()
        return result.as_dict()

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


# ─────────────────────────────────────────────────────────────────────────────
# OPTION 5 — ROI Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/roi/record",
    summary="Manually record a completed fix for ROI tracking",
    status_code=status.HTTP_201_CREATED,
)
async def roi_record(
    req: RecordFixRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Insert one ROI record into the database.

    This endpoint is intended for external callers (e.g. CI scripts, webhook
    consumers) that exist outside the LangGraph pipeline. The pipeline itself
    records fixes automatically via `recovery_complete_node`.
    """
    try:
        row = await record_fix(
            fix_id=req.fix_id,
            language=req.language,
            severity=req.severity,
            mttr_before_min=req.mttr_before_min,
            mttr_after_min=req.mttr_after_min,
            was_automated=req.was_automated,
            repository=req.repository,
            session=session,
        )
        await session.commit()
        return {
            "fix_id": row.fix_id,
            "language": row.language,
            "severity": row.severity,
            "human_hours_saved": row.human_hours_saved,
            "cost_saved_usd": row.cost_saved_usd,
            "incident_prevented": row.incident_prevented,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.get(
    "/roi/dashboard",
    summary="Full ROI metrics for Mission Control dashboard",
)
async def roi_dashboard(
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Rolling window in days for the burndown series.",
    ),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Returns all ROI metrics aggregated across every recorded fix.

    Identical to `GET /api/v1/roi/dashboard` but exposed under the v2 prefix
    so dashboard clients can use a single base URL for all ARE v2 features.
    """
    try:
        import os
        if os.environ.get("ENABLE_REAL_METRICS", "false").lower() == "true":
            from backend.recovery_ext.metrics_service import get_real_dashboard_data
            data = await get_real_dashboard_data(days=days, session=session)
            return data.as_dict()

        data = await get_dashboard_data(days=days, session=session)
        return data.as_dict()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.get(
    "/roi/weekly-report",
    summary="Markdown weekly ROI learning report",
    response_class=PlainTextResponse,
)
async def roi_weekly_report(
    session: AsyncSession = Depends(get_db),
) -> str:
    """
    Returns a Markdown table summarising the last 7 days of ROI metrics.
    Drop into Slack digests, GitHub PR comments, or scheduled emails.
    """
    try:
        return await weekly_report(session=session)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.get(
    "/roi/records",
    summary="Recent individual fix records",
)
async def roi_records(
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
        description="Maximum records to return, most recent first.",
    ),
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Per-fix drill-down data for the dashboard table view."""
    try:
        return await get_recent_records(limit=limit, session=session)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
