"""
ARE — Economic ROI Tracker: API Router
=======================================
Mounts under /api/v1/roi and exposes three endpoints:

  GET  /api/v1/roi/dashboard          → ROIDashboardData (JSON)
  GET  /api/v1/roi/weekly-report      → Markdown weekly report (text)
  GET  /api/v1/roi/records            → Raw list of recent FixRecord rows

All endpoints use the existing AsyncSession dependency (get_db).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.services.roi import (
    ROIDashboardData,
    get_dashboard_data,
    get_recent_records,
    weekly_report,
)


router = APIRouter(
    prefix="/api/v1/roi",
    tags=["ROI"],
)


@router.get(
    "/dashboard",
    summary="Economic ROI dashboard metrics",
    response_model=None,
)
async def roi_dashboard(
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Rolling window in days for burndown charts.",
    ),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return all ROI metrics aggregated across every recorded fix.

    Cumulative totals (total_cost_saved_usd, total_fixes, …) are all-time.
    Burndown series (daily_hours_saved, daily_fixes) cover the last ``days`` days.
    """
    import os
    if os.environ.get("ENABLE_REAL_METRICS", "false").lower() == "true":
        from backend.recovery_ext.metrics_service import get_real_dashboard_data
        data = await get_real_dashboard_data(days=days, session=session)
        return data.as_dict()

    data: ROIDashboardData = await get_dashboard_data(
        days=days,
        session=session,
    )
    return data.as_dict()


@router.get(
    "/weekly-report",
    summary="Markdown-formatted weekly ROI learning report",
    response_class=PlainTextResponse,
)
async def roi_weekly_report(
    session: AsyncSession = Depends(get_db),
) -> str:
    """
    Returns a Markdown table summarising the last 7 days of ROI metrics.
    Suitable for embedding in Slack digests, GitHub comments, or email.
    """
    return await weekly_report(session=session)


@router.get(
    "/records",
    summary="Recent individual fix records",
    response_model=None,
)
async def roi_records(
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
        description="Maximum number of records to return (most recent first).",
    ),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    Return the N most recent FixRecord rows as JSON objects.
    Useful for per-fix drill-down views on the dashboard.
    """
    return await get_recent_records(limit=limit, session=session)


@router.get(
    "/blocked-incidents",
    summary="Count of BLOCKED_BY_POLICY incidents",
    response_model=None,
)
async def roi_blocked_incidents() -> dict:
    """
    Return the count of incidents blocked by policy (score > 0.7).
    Reads from the Phase 1 `escalations` table (additive; never touches existing tables).
    """
    import os
    if os.environ.get("ENABLE_REAL_METRICS", "false").lower() == "true":
        from backend.db.session import AsyncSessionLocal
        from backend.recovery_ext.metrics_service import get_real_blocked_count
        async with AsyncSessionLocal() as session:
            count = await get_real_blocked_count(session=session)
        return {"blocked_incidents": count}

    from backend.recovery_ext.human_escalation import get_blocked_count
    count = await get_blocked_count()
    return {"blocked_incidents": count}
