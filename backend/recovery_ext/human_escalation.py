"""
recovery_ext/human_escalation.py
──────────────────────────────────
Phase 5: BLOCK path escalation.

When decision == BLOCK (or approval rejected / timed out):
  1. Emits a [HUMAN_ESCALATION_NODE] telemetry event with score + top factors.
  2. Tries to create a GitHub Issue on the target repository.
  3. Persists the escalation record to `escalations` table (Phase 1 DB only).
  4. Sets incident status → FAILED with failure_reason = "BLOCKED_BY_POLICY".

Only active when ENABLE_BLOCK_ESCALATION=true.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from backend.db.models import IncidentStatus
from backend.db.session import AsyncSessionLocal
from backend.orchestration.telemetry import emit_node_event
from backend.services.incidents import update_incident_state
from backend.recovery_ext.flags import get_flags

logger = logging.getLogger(__name__)

router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────────
# Escalation result (returned to caller / stored)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class EscalationResult:
    incident_id: str
    failure_reason: str
    risk_score: float
    top_factors: list[dict]
    issue_url: str | None  # None if GitHub not configured or call failed
    escalated_at: str


# ──────────────────────────────────────────────────────────────────────────────
# DB helpers  (escalations table – Phase 1 stores only)
# ──────────────────────────────────────────────────────────────────────────────

async def _init_escalations_table() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                CREATE TABLE IF NOT EXISTS escalations (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id  VARCHAR NOT NULL UNIQUE,
                    failure_reason VARCHAR NOT NULL DEFAULT 'BLOCKED_BY_POLICY',
                    risk_score   REAL NOT NULL DEFAULT 0.0,
                    top_factors  TEXT,
                    issue_url    VARCHAR,
                    repository   VARCHAR,
                    affected_file VARCHAR,
                    escalated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """)
        )
        await session.commit()


async def _store_escalation(result: EscalationResult, repository: str, affected_file: str) -> None:
    import json
    try:
        await _init_escalations_table()
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    INSERT INTO escalations
                        (incident_id, failure_reason, risk_score, top_factors,
                         issue_url, repository, affected_file, escalated_at)
                    VALUES (:iid, :fr, :rs, :tf, :iu, :repo, :af, :ts)
                    ON CONFLICT (incident_id) DO UPDATE
                        SET issue_url = excluded.issue_url,
                            risk_score = excluded.risk_score
                """),
                {
                    "iid": result.incident_id,
                    "fr":  result.failure_reason,
                    "rs":  result.risk_score,
                    "tf":  json.dumps(result.top_factors),
                    "iu":  result.issue_url,
                    "repo": repository,
                    "af":  affected_file,
                    "ts":  result.escalated_at,
                },
            )
            await session.commit()
    except Exception as exc:
        logger.error("[HUMAN_ESCALATION] DB store failed: %s", exc)


async def get_blocked_count() -> int:
    """Returns the total count of BLOCKED_BY_POLICY incidents from the escalations table."""
    try:
        await _init_escalations_table()
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT COUNT(*) FROM escalations WHERE failure_reason = 'BLOCKED_BY_POLICY'")
            )
            row = result.fetchone()
            return row[0] if row else 0
    except Exception:
        return 0


# ──────────────────────────────────────────────────────────────────────────────
# GitHub issue creation (best-effort, never raises)
# ──────────────────────────────────────────────────────────────────────────────

def _create_github_issue(
    *,
    repository_full_name: str,
    incident_id: str,
    affected_file: str,
    error_message: str,
    risk_score: float,
    top_factors: list[dict],
    failure_reason: str,
) -> str | None:
    """
    Create a GitHub Issue for the BLOCK escalation.
    Returns the issue URL or None if creation fails / not configured.
    Never logs secrets.
    """
    try:
        from github import Github, Auth
        from github.GithubException import GithubException, RateLimitExceededException
        from backend.config.github_config import GitHubSettings

        settings = GitHubSettings()  # type: ignore[call-arg]
        if not settings.token:
            logger.warning("[HUMAN_ESCALATION] GITHUB_TOKEN not configured; skipping issue creation.")
            return None

        try:
            auth = Auth.Token(settings.token)
            gh = Github(auth=auth, timeout=15)
        except Exception:
            gh = Github(login_or_token=settings.token, timeout=15)

        repo = gh.get_repo(repository_full_name)

        factors_md = "\n".join(
            f"| `{f.get('factor', '?')}` | `{f.get('contribution', f.get('value', 0)):.3f}` | {f.get('explanation', '')} |"
            for f in top_factors[:4]
        )

        body = f"""\
## 🚨 Automated Patch Withheld — Policy Block

| Field | Value |
|-------|-------|
| **Incident ID** | `{incident_id}` |
| **Affected File** | `{affected_file}` |
| **Risk Score** | `{risk_score:.4f}` (threshold: 0.70) |
| **Failure Reason** | `{failure_reason}` |
| **Timestamp** | {datetime.now(timezone.utc).isoformat()} |

### Risk Breakdown

| Factor | Score | Explanation |
|--------|-------|-------------|
{factors_md}

### Error Context

```
{error_message[:2000]}
```

---

**The autonomous recovery agent detected a high-risk change and withheld the automated patch.**
A human engineer must review and apply the fix manually.

> _This issue was created automatically by the Autonomous Recovery Engine._
"""

        issue = repo.create_issue(
            title=f"[AUTO-RECOVERY BLOCKED] {incident_id} — Risk {risk_score:.2f}",
            body=body,
            labels=[],  # safe default; no label creation attempted
        )
        logger.info("[HUMAN_ESCALATION] GitHub issue created: %s", issue.html_url)
        return issue.html_url

    except Exception as exc:
        # Broad catch: rate limit, auth failure, repo not found — all non-fatal
        logger.warning("[HUMAN_ESCALATION] GitHub issue creation failed (non-fatal): %s", exc)
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Main escalation entry point (called from graph node or approval_gate timeout)
# ──────────────────────────────────────────────────────────────────────────────

async def run_human_escalation(state: dict[str, Any]) -> EscalationResult:
    """
    Execute the full BLOCK escalation sequence:
      1. Emit [HUMAN_ESCALATION_NODE] event.
      2. Create GitHub Issue (best-effort).
      3. Persist to escalations table.
      4. Mark incident FAILED.
    """
    flags = get_flags()
    if not flags.enable_block_escalation:
        logger.debug("[HUMAN_ESCALATION] flag disabled; skipping escalation.")
        return EscalationResult(
            incident_id=state.get("incident_id", "unknown"),
            failure_reason="BLOCKED_BY_POLICY",
            risk_score=0.0,
            top_factors=[],
            issue_url=None,
            escalated_at=datetime.now(timezone.utc).isoformat(),
        )

    incident_id: str = state.get("incident_id", "unknown")
    risk_data: dict = state.get("explainable_risk", {})
    risk_score: float = float(risk_data.get("score", 0.0))
    breakdown: list = risk_data.get("breakdown", [])
    failure_reason: str = state.get("failure_reason", "BLOCKED_BY_POLICY")

    # Top 4 factors by contribution (descending)
    top_factors = sorted(
        breakdown,
        key=lambda f: float(f.get("contribution", f.get("value", 0))),
        reverse=True,
    )[:4]

    repo_full: str = state.get("repository_full_name", "")
    affected_file: str = (state.get("root_cause_analysis") or {}).get("affected_file", "")
    error_msg: str = state.get("triage_context", "")

    # 1 — Telemetry event
    await emit_node_event(
        incident_id=incident_id,
        event_type="human_escalation",
        node_name="human_escalation_node",
        message=(
            f"[HUMAN_ESCALATION_NODE] BLOCK: risk_score={risk_score:.4f}, "
            f"reason={failure_reason}, "
            f"top_factor={top_factors[0]['factor'] if top_factors else 'N/A'}"
        ),
        metadata={
            "risk_score": risk_score,
            "failure_reason": failure_reason,
            "top_factors": top_factors,
        },
        retry_count=state.get("retry_count", 0),
    )

    # 2 — GitHub Issue (best-effort, synchronous in threadpool)
    import asyncio
    issue_url: str | None = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: _create_github_issue(
            repository_full_name=repo_full,
            incident_id=incident_id,
            affected_file=affected_file,
            error_message=error_msg,
            risk_score=risk_score,
            top_factors=top_factors,
            failure_reason=failure_reason,
        ),
    )

    escalated_at = datetime.now(timezone.utc).isoformat()
    result = EscalationResult(
        incident_id=incident_id,
        failure_reason=failure_reason,
        risk_score=risk_score,
        top_factors=top_factors,
        issue_url=issue_url,
        escalated_at=escalated_at,
    )

    # 3 — Persist
    await _store_escalation(result, repository=repo_full, affected_file=affected_file)

    # 4 — Mark incident FAILED
    try:
        await update_incident_state(
            incident_id=incident_id,
            status=IncidentStatus.FAILED,
        )
    except Exception as exc:
        logger.error("[HUMAN_ESCALATION] Failed to update incident status: %s", exc)

    # 5 — Emit final blocked event (so SSE listeners see it)
    await emit_node_event(
        incident_id=incident_id,
        event_type="incident_blocked",
        node_name="human_escalation_node",
        message=(
            f"[HUMAN_ESCALATION_NODE] Incident FAILED. "
            f"{'Issue: ' + issue_url if issue_url else 'No GitHub issue created.'}"
        ),
        metadata={
            "issue_url": issue_url,
            "risk_score": risk_score,
            "status": "FAILED",
        },
        retry_count=state.get("retry_count", 0),
    )

    return result
