from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Incident, IncidentStatus
from backend.config import get_settings



class IncidentNotFoundError(LookupError):
    """Raised when an incident cannot be found."""


class IncidentStateError(ValueError):
    """Raised when an invalid incident state transition is requested."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def create_incident(
    *,
    session: AsyncSession,
    incident_id: str,
    github_payload: dict[str, Any],
    repository: str,
    branch: str,
    commit_sha: str | None,
    is_mock_mode: bool,
    is_shadow_mode: bool | None = None,
    repository_owner: str = "",
    repository_name: str = "",
    repository_full_name: str = "",
    repository_url: str = "",
    default_branch: str = "main",
    source_branch: str = "",
    workflow_run_id: str = "",
    user_id: str | None = None,
    username: str | None = None,
    session_id: str | None = None,
) -> Incident:
    """Create and flush a new incident."""
    settings = get_settings()
    shadow = settings.shadow_mode if is_shadow_mode is None else is_shadow_mode

    incident = Incident(
        incident_id=incident_id,
        status=IncidentStatus.RECEIVED,
        repository=repository,
        branch=branch,
        commit_sha=commit_sha,
        repository_owner=repository_owner,
        repository_name=repository_name,
        repository_full_name=repository_full_name,
        repository_url=repository_url,
        default_branch=default_branch,
        source_branch=source_branch,
        workflow_run_id=workflow_run_id,
        user_id=user_id,
        username=username,
        session_id=session_id,
        is_mock_mode=is_mock_mode,
        github_payload=github_payload,
        triage_context="",
        root_cause_analysis={},
        explainable_risk={
            "score": 0.0,
            "breakdown": [],
            "decision": "BLOCK",
        },
        action_decision="BLOCK",
        human_approved=False,
        current_patch_diff="",
        test_results={
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
        },
        retry_count=0,
        pr_url="",
        patch_explanation="",
        generated_test_code="",
        similar_past_cases=[],
        learning_confidence_boost=0.0,
        is_shadow_mode=shadow,
    )

    session.add(incident)

    await session.flush()

    return incident


async def get_incident(
    *,
    session: AsyncSession,
    incident_id: str,
) -> Incident:
    """Retrieve an incident by its public incident ID."""

    statement = select(Incident).where(
        Incident.incident_id == incident_id
    )

    result = await session.execute(statement)

    incident = result.scalar_one_or_none()

    if incident is None:
        raise IncidentNotFoundError(
            f"Incident '{incident_id}' was not found."
        )

    return incident


async def list_incidents(
    *,
    session: AsyncSession,
    repository: str | None = None,
    repository_owner: str | None = None,
    username: str | None = None,
    limit: int = 50,
) -> list[Incident]:
    """Retrieve recent incidents, optionally filtered by repository, owner, or authenticated user."""
    statement = select(Incident).order_by(Incident.created_at.desc()).limit(limit)
    if repository:
        statement = statement.where(Incident.repository == repository)
    if repository_owner:
        statement = statement.where(Incident.repository_owner == repository_owner)
    if username:
        statement = statement.where(
            (Incident.username == username) | (Incident.repository_owner == username)
        )

    result = await session.execute(statement)
    return list(result.scalars().all())


async def approve_incident(
    *,
    session: AsyncSession,
    incident: Incident,
    approved: bool,
) -> Incident:
    """
    Apply a human decision.

    Approval is only meaningful while the incident is waiting for a human.
    """

    if incident.status != IncidentStatus.AWAITING_APPROVAL:
        raise IncidentStateError(
            "Incident is not awaiting human approval."
        )

    incident.human_approved = approved

    if approved:
        incident.status = IncidentStatus.REPAIRING
    else:
        incident.status = IncidentStatus.ESCALATED

    incident.updated_at = _utc_now()

    await session.flush()

    return incident


def build_recovery_state(
    incident: Incident,
) -> dict[str, Any]:
    """
    Convert the persisted incident into the canonical LangGraph state.

    This function intentionally uses the Phase 1 factory so every field
    is initialized consistently.
    """
    from backend.orchestration.state_factory import (
        create_initial_recovery_state,
    )
    settings = get_settings()

    state = create_initial_recovery_state(
        incident_id=incident.incident_id,
        github_payload=incident.github_payload,
        is_mock_mode=incident.is_mock_mode,
        is_shadow_mode=incident.is_shadow_mode if hasattr(incident, "is_shadow_mode") else settings.shadow_mode,
        user_id=getattr(incident, "user_id", "") or "",
        username=getattr(incident, "username", "") or "",
        session_id=getattr(incident, "session_id", "") or "",
    )

    state["triage_context"] = incident.triage_context
    state["root_cause_analysis"] = incident.root_cause_analysis
    state["explainable_risk"] = incident.explainable_risk
    state["action_decision"] = incident.action_decision
    state["human_approved"] = incident.human_approved
    state["current_patch_diff"] = incident.current_patch_diff
    state["test_results"] = incident.test_results
    state["retry_count"] = incident.retry_count
    state["pr_url"] = incident.pr_url
    state["patch_explanation"] = getattr(incident, "patch_explanation", "") or ""
    state["generated_test_code"] = getattr(incident, "generated_test_code", "") or ""
    state["similar_past_cases"] = getattr(incident, "similar_past_cases", []) or []
    state["learning_confidence_boost"] = getattr(incident, "learning_confidence_boost", 0.0) or 0.0
    state["is_shadow_mode"] = getattr(incident, "is_shadow_mode", True)
    state["user_id"] = getattr(incident, "user_id", "") or ""
    state["username"] = getattr(incident, "username", "") or ""
    state["session_id"] = getattr(incident, "session_id", "") or ""

    return state


async def apply_state_to_incident(
    *,
    incident: Incident,
    state: dict[str, Any],
) -> Incident:
    """Persist LangGraph state back onto the incident."""

    incident.triage_context = str(
        state.get("triage_context", "")
    )

    incident.root_cause_analysis = dict(
        state.get("root_cause_analysis", {})
    )

    incident.explainable_risk = dict(
        state.get("explainable_risk", {})
    )

    incident.action_decision = str(
        state.get("action_decision", "BLOCK")
    )

    incident.human_approved = bool(
        state.get("human_approved", False)
    )

    incident.current_patch_diff = str(
        state.get("current_patch_diff", "")
    )

    incident.test_results = dict(
        state.get("test_results", {})
    )

    incident.retry_count = int(
        state.get("retry_count", 0)
    )

    incident.pr_url = str(
        state.get("pr_url", "")
    )

    incident.patch_explanation = str(
        state.get("patch_explanation", "")
    )

    incident.generated_test_code = str(
        state.get("generated_test_code", "")
    )

    incident.similar_past_cases = list(
        state.get("similar_past_cases", [])
    )

    incident.learning_confidence_boost = float(
        state.get("learning_confidence_boost", 0.0)
    )

    if "is_shadow_mode" in state:
        incident.is_shadow_mode = bool(state.get("is_shadow_mode", True))

    incident.updated_at = _utc_now()

    return incident


async def update_incident_state(
    incident_id: str,
    *,
    status: IncidentStatus | str | None = None,
    triage_context: str | None = None,
    root_cause_analysis: dict[str, Any] | None = None,
    current_patch_diff: str | None = None,
    test_results: dict[str, Any] | None = None,
    explainable_risk: dict[str, Any] | None = None,
    action_decision: str | None = None,
    human_approved: bool | None = None,
    pr_url: str | None = None,
    patch_explanation: str | None = None,
    generated_test_code: str | None = None,
    retry_count: int | None = None,
) -> Incident | None:
    """Safely update and persist mutable incident state to database."""
    from backend.db.session import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as session:
            try:
                incident = await get_incident(session=session, incident_id=incident_id)
            except IncidentNotFoundError:
                return None

            if status is not None:
                incident.status = status if isinstance(status, IncidentStatus) else IncidentStatus(status)
            if triage_context is not None:
                incident.triage_context = triage_context
            if root_cause_analysis is not None:
                incident.root_cause_analysis = dict(root_cause_analysis)
            if current_patch_diff is not None:
                incident.current_patch_diff = current_patch_diff
            if test_results is not None:
                incident.test_results = dict(test_results)
            if explainable_risk is not None:
                incident.explainable_risk = dict(explainable_risk)
            if action_decision is not None:
                incident.action_decision = action_decision
            if human_approved is not None:
                incident.human_approved = human_approved
            if pr_url is not None:
                incident.pr_url = pr_url
            if patch_explanation is not None:
                incident.patch_explanation = patch_explanation
            if generated_test_code is not None:
                incident.generated_test_code = generated_test_code
            if retry_count is not None:
                incident.retry_count = retry_count

            incident.updated_at = _utc_now()
            await session.commit()
            return incident
    except Exception:
        return None


