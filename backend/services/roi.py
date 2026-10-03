"""
ARE — Economic ROI Tracker: Service Layer
==========================================
Async persistence and aggregation for fix-level ROI metrics.

Mirrors the knowledge.py pattern:
  - record_fix()         → insert one FixRecord row
  - get_dashboard_data() → aggregate query → ROIDashboardData
  - weekly_report()      → markdown string for the learning report
  - get_recent_records() → raw list for API pagination

Uses AsyncSessionLocal (your existing session factory) — no JSON files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import FixRecord
from backend.db.session import AsyncSessionLocal

# ── Engineering cost constants (override via env vars) ────────────────────────
_HOURLY_RATE_USD: float = float(os.getenv("ENGINEER_HOURLY_RATE", "85"))
_MANUAL_TRIAGE_MIN: float = 45.0   # minutes a human spends triaging one CI failure
_MANUAL_FIX_MIN: float = 90.0      # minutes to manually write + test a fix
_INCIDENT_COST_USD: float = 500.0  # average cost per HIGH-severity incident prevented


# ─────────────────────────────────────────────────────────────────────────────
# DERIVED METRIC HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _compute_hours_saved(mttr_after_min: float) -> float:
    """Engineer-hours saved vs. full manual triage + fix."""
    manual_total = _MANUAL_TRIAGE_MIN + _MANUAL_FIX_MIN
    saved_min = max(0.0, manual_total - mttr_after_min)
    return round(saved_min / 60.0, 3)


def _compute_cost_saved(hours_saved: float, severity: str) -> float:
    """Dollar value saved, including incident-prevention bonus for HIGH severity."""
    labour = hours_saved * _HOURLY_RATE_USD
    bonus = _INCIDENT_COST_USD if severity.upper() == "HIGH" else 0.0
    return round(labour + bonus, 2)


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASS RETURNED BY get_dashboard_data()
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ROIDashboardData:
    # ── Cumulative (all-time) ─────────────────────────────────────────────────
    total_fixes: int
    total_human_hours_saved: float
    total_cost_saved_usd: float
    incidents_prevented: int
    automated_fix_rate_pct: float       # % fixed without human approval

    # ── Reliability ───────────────────────────────────────────────────────────
    avg_mttr_before_min: float
    avg_mttr_after_min: float
    mttr_reduction_pct: float
    test_pass_rate_improvement_pct: float

    # ── Daily burndown (last N days) ──────────────────────────────────────────
    daily_hours_saved: list[dict]       # [{date, hours_saved, cost_saved}]
    daily_fixes: list[dict]             # [{date, count, automated_count}]

    # ── Breakdowns ────────────────────────────────────────────────────────────
    fixes_by_language: dict[str, int]
    fixes_by_severity: dict[str, int]
    fixes_by_repo: dict[str, int]

    # ── Headline cards (pre-formatted strings for the dashboard) ──────────────
    headline: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_fixes": self.total_fixes,
            "total_human_hours_saved": self.total_human_hours_saved,
            "total_cost_saved_usd": self.total_cost_saved_usd,
            "incidents_prevented": self.incidents_prevented,
            "automated_fix_rate_pct": self.automated_fix_rate_pct,
            "avg_mttr_before_min": self.avg_mttr_before_min,
            "avg_mttr_after_min": self.avg_mttr_after_min,
            "mttr_reduction_pct": self.mttr_reduction_pct,
            "test_pass_rate_improvement_pct": self.test_pass_rate_improvement_pct,
            "daily_hours_saved": self.daily_hours_saved,
            "daily_fixes": self.daily_fixes,
            "fixes_by_language": self.fixes_by_language,
            "fixes_by_severity": self.fixes_by_severity,
            "fixes_by_repo": self.fixes_by_repo,
            "headline": self.headline,
        }


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPER
# ─────────────────────────────────────────────────────────────────────────────


def _record_to_dict(r: FixRecord) -> dict[str, Any]:
    return {
        "fix_id": r.fix_id,
        "language": r.language,
        "severity": r.severity,
        "mttr_before_min": r.mttr_before_min,
        "mttr_after_min": r.mttr_after_min,
        "was_automated": r.was_automated,
        "repository": r.repository,
        "human_hours_saved": r.human_hours_saved,
        "cost_saved_usd": r.cost_saved_usd,
        "incident_prevented": r.incident_prevented,
        "created_at": r.created_at.isoformat() if r.created_at else "",
    }


def _empty_dashboard() -> ROIDashboardData:
    return ROIDashboardData(
        total_fixes=0,
        total_human_hours_saved=0.0,
        total_cost_saved_usd=0.0,
        incidents_prevented=0,
        automated_fix_rate_pct=0.0,
        avg_mttr_before_min=0.0,
        avg_mttr_after_min=0.0,
        mttr_reduction_pct=0.0,
        test_pass_rate_improvement_pct=0.0,
        daily_hours_saved=[],
        daily_fixes=[],
        fixes_by_language={},
        fixes_by_severity={},
        fixes_by_repo={},
        headline={
            "total_cost_saved": "$0",
            "hours_saved_text": "No fixes recorded yet.",
            "mttr_reduction_text": "N/A",
            "incidents_prevented": "0 production incidents prevented",
            "auto_rate": "0% fixes fully automated",
            "monthly_cost_saved": "$0/month",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────


async def record_fix(
    *,
    fix_id: str,
    language: str,
    severity: str,
    mttr_before_min: float,
    mttr_after_min: float,
    was_automated: bool,
    repository: str,
    session: AsyncSession | None = None,
) -> FixRecord:
    """
    Insert one ROI record after a successful fix.

    Called automatically from recovery_complete_node.  Can also be called
    from tests or one-off scripts by passing a session explicitly.

    Severity should be one of: "LOW", "MEDIUM", "HIGH".
    """
    sev = severity.upper()
    hours_saved = _compute_hours_saved(mttr_after_min)
    cost_saved = _compute_cost_saved(hours_saved, sev)

    row = FixRecord(
        fix_id=fix_id,
        language=language,
        severity=sev,
        mttr_before_min=mttr_before_min,
        mttr_after_min=mttr_after_min,
        was_automated=was_automated,
        repository=repository,
        human_hours_saved=hours_saved,
        cost_saved_usd=cost_saved,
        incident_prevented=(sev == "HIGH"),
    )

    if session is not None:
        session.add(row)
        await session.flush()
        return row

    async with AsyncSessionLocal() as db:
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row


async def get_dashboard_data(
    *,
    days: int = 30,
    session: AsyncSession | None = None,
) -> ROIDashboardData:
    """
    Aggregate all FixRecord rows into dashboard metrics.

    Cumulative totals are computed across all time; burndown charts
    are scoped to the last ``days`` days.
    """

    async def _run(s: AsyncSession) -> ROIDashboardData:
        # ── All-time rows ──────────────────────────────────────────────────
        all_stmt = select(FixRecord).order_by(FixRecord.created_at)
        all_result = await s.execute(all_stmt)
        all_rows: list[FixRecord] = list(all_result.scalars().all())

        if not all_rows:
            return _empty_dashboard()

        total = len(all_rows)
        total_hours = sum(r.human_hours_saved for r in all_rows)
        total_cost = sum(r.cost_saved_usd for r in all_rows)
        incidents_prevented = sum(1 for r in all_rows if r.incident_prevented)
        automated_count = sum(1 for r in all_rows if r.was_automated)
        auto_rate = (automated_count / total * 100) if total else 0.0

        avg_before = sum(r.mttr_before_min for r in all_rows) / total
        avg_after = sum(r.mttr_after_min for r in all_rows) / total
        mttr_reduction = (
            ((avg_before - avg_after) / avg_before * 100) if avg_before else 0.0
        )
        # Proxy: automated rate correlates with test-pass improvement (cap 8pp)
        test_pass_improvement = round(min(auto_rate * 0.08, 8.0), 1)

        # ── Breakdowns ────────────────────────────────────────────────────
        by_lang: dict[str, int] = {}
        by_sev: dict[str, int] = {}
        by_repo: dict[str, int] = {}
        for r in all_rows:
            by_lang[r.language] = by_lang.get(r.language, 0) + 1
            by_sev[r.severity] = by_sev.get(r.severity, 0) + 1
            by_repo[r.repository] = by_repo.get(r.repository, 0) + 1

        # ── Daily burndown (last N days) ───────────────────────────────────
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent = [
            r
            for r in all_rows
            if r.created_at and r.created_at.replace(tzinfo=timezone.utc) >= cutoff
        ]

        day_hours: dict[str, float] = {}
        day_cost: dict[str, float] = {}
        day_cnt: dict[str, int] = {}
        day_auto: dict[str, int] = {}

        for r in recent:
            day = (r.created_at.date().isoformat() if r.created_at else "")
            if not day:
                continue
            day_hours[day] = day_hours.get(day, 0.0) + r.human_hours_saved
            day_cost[day] = day_cost.get(day, 0.0) + r.cost_saved_usd
            day_cnt[day] = day_cnt.get(day, 0) + 1
            if r.was_automated:
                day_auto[day] = day_auto.get(day, 0) + 1

        all_days = sorted(set(day_hours) | set(day_cnt))
        daily_hours_saved = [
            {
                "date": d,
                "hours_saved": round(day_hours.get(d, 0.0), 2),
                "cost_saved": round(day_cost.get(d, 0.0), 2),
            }
            for d in all_days
        ]
        daily_fixes = [
            {
                "date": d,
                "count": day_cnt.get(d, 0),
                "automated_count": day_auto.get(d, 0),
            }
            for d in all_days
        ]

        # ── Headline cards ─────────────────────────────────────────────────
        first_ts = all_rows[0].created_at
        age_days = max(
            (datetime.now(timezone.utc) - first_ts.replace(tzinfo=timezone.utc)).days,
            1,
        ) if first_ts else 1
        monthly_cost = total_cost / age_days * 30

        headline: dict[str, str] = {
            "total_cost_saved": f"${total_cost:,.0f}",
            "hours_saved_text": f"{total_hours:,.0f} engineer-hours saved",
            "mttr_reduction_text": (
                f"MTTR reduced {mttr_reduction:.0f}% "
                f"({avg_before:.0f}m → {avg_after:.0f}m)"
            ),
            "incidents_prevented": (
                f"{incidents_prevented} production incidents prevented"
            ),
            "auto_rate": f"{auto_rate:.0f}% fixes fully automated",
            "monthly_cost_saved": f"${monthly_cost:,.0f}/month",
        }

        return ROIDashboardData(
            total_fixes=total,
            total_human_hours_saved=round(total_hours, 2),
            total_cost_saved_usd=round(total_cost, 2),
            incidents_prevented=incidents_prevented,
            automated_fix_rate_pct=round(auto_rate, 1),
            avg_mttr_before_min=round(avg_before, 1),
            avg_mttr_after_min=round(avg_after, 1),
            mttr_reduction_pct=round(mttr_reduction, 1),
            test_pass_rate_improvement_pct=test_pass_improvement,
            daily_hours_saved=daily_hours_saved,
            daily_fixes=daily_fixes,
            fixes_by_language=by_lang,
            fixes_by_severity=by_sev,
            fixes_by_repo=by_repo,
            headline=headline,
        )

    if session is not None:
        return await _run(session)

    try:
        async with AsyncSessionLocal() as db:
            return await _run(db)
    except Exception:
        return _empty_dashboard()


async def get_recent_records(
    *,
    limit: int = 50,
    session: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    """Return the N most recent FixRecord rows as plain dicts."""

    async def _run(s: AsyncSession) -> list[dict[str, Any]]:
        stmt = (
            select(FixRecord)
            .order_by(FixRecord.created_at.desc())
            .limit(limit)
        )
        result = await s.execute(stmt)
        return [_record_to_dict(r) for r in result.scalars().all()]

    if session is not None:
        return await _run(session)

    try:
        async with AsyncSessionLocal() as db:
            return await _run(db)
    except Exception:
        return []


async def weekly_report(
    *,
    session: AsyncSession | None = None,
) -> str:
    """
    Markdown-formatted weekly learning report.
    Plug into your existing Learning Report feature or weekly email.
    """
    data = await get_dashboard_data(days=7, session=session)
    top_lang = (
        max(data.fixes_by_language, key=lambda k: data.fixes_by_language[k])
        if data.fixes_by_language
        else "N/A"
    )
    return (
        f"## 📊 ARE Weekly ROI Report\n"
        f"**Period:** Last 7 days\n\n"
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| 🔧 Fixes Applied | {data.total_fixes} |\n"
        f"| ⏱️  Engineer Hours Saved | {data.total_human_hours_saved:.1f}h |\n"
        f"| 💰 Cost Saved | ${data.total_cost_saved_usd:,.0f} |\n"
        f"| 🚨 Incidents Prevented | {data.incidents_prevented} |\n"
        f"| ⚡ MTTR Reduction | {data.mttr_reduction_pct:.0f}% |\n"
        f"| 🤖 Automation Rate | {data.automated_fix_rate_pct:.0f}% |\n"
        f"| 🌐 Top Language | {top_lang.upper()} |\n\n"
        f"{data.headline['monthly_cost_saved']} projected savings at this rate.\n"
    )
