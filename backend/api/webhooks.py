from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db.models import AuditEventType, Incident
from backend.db.session import get_db
from backend.orchestration.runtime import recovery_runtime
from backend.orchestration.state_factory import (
    create_initial_recovery_state,
)
from backend.schemas.audit import AuditEventCreate
from backend.services.audit import record_audit_event
from backend.services.github_webhook import (
    GitHubWebhookError,
    parse_github_webhook,
    verify_github_signature,
)
from backend.services.incidents import create_incident
from backend.services.telemetry import telemetry_manager


router = APIRouter(
    prefix="/webhook",
    tags=["GitHub Webhooks"],
)


@router.post(
    "/github",
    status_code=status.HTTP_202_ACCEPTED,
)
async def github_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
    x_github_event: str | None = Header(
        default=None,
        alias="X-GitHub-Event",
    ),
    x_hub_signature_256: str | None = Header(
        default=None,
        alias="X-Hub-Signature-256",
    ),
) -> dict[str, object]:
    settings = get_settings()

    raw_body = await request.body()

    if len(raw_body) > settings.webhook_max_body_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                "GitHub webhook payload exceeds "
                "the configured size limit."
            ),
        )

    if not x_github_event:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-GitHub-Event header is required.",
        )

    if settings.github_webhook_secret and not verify_github_signature(
        payload=raw_body,
        signature_header=x_hub_signature_256,
        secret=settings.github_webhook_secret,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid GitHub webhook signature.",
        )

    try:
        payload = json.loads(
            raw_body.decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub webhook body is not valid JSON.",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "GitHub webhook payload must be a JSON object."
            ),
        )

    try:
        parsed = parse_github_webhook(
            event_name=x_github_event,
            payload=payload,
        )
    except GitHubWebhookError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    is_mock_mode = settings.allow_mock_mode and (
        request.headers.get(
            "X-Recovery-Mock",
            "",
        ).lower()
        == "true"
    )

    # 1. Non-failure filter for workflow_run events
    if parsed.event_name in {"workflow_run", "check_run"} and not parsed.is_failure_event and not is_mock_mode:
        return {
            "accepted": False,
            "message": f"GitHub {parsed.event_name} event conclusion '{parsed.conclusion or 'unknown'}' is not a failure. Remediation not required.",
        }

    # 2. Idempotency check: don't create duplicate incidents for the same workflow run
    if parsed.github_run_id:
        stmt = (
            select(Incident)
            .where(Incident.repository == parsed.repository)
            .order_by(Incident.created_at.desc())
            .limit(20)
        )
        res = await session.execute(stmt)
        candidates = res.scalars().all()
        for cand in candidates:
            cand_payload = cand.github_payload or {}
            cand_run_id = str(
                cand_payload.get("workflow_run", {}).get("id", "")
            ) or str(cand_payload.get("id", ""))
            if cand_run_id and cand_run_id == str(parsed.github_run_id):
                return {
                    "accepted": True,
                    "incident_id": cand.incident_id,
                    "repository": cand.repository,
                    "branch": cand.branch,
                    "is_mock_mode": cand.is_mock_mode,
                    "duplicate": True,
                    "message": "Incident already exists for this GitHub workflow run.",
                }

    incident_id = f"inc_{uuid.uuid4().hex}"

    owner = payload.get("repository", {}).get("owner", {}).get("login", "")
    repo_name = payload.get("repository", {}).get("name", "")
    extracted_branch = payload.get("ref", "").replace("refs/heads/", "") if payload.get("ref") else parsed.branch
    extracted_commit_sha = payload.get("after") or payload.get("head_commit", {}).get("id") or parsed.commit_sha
    repo_url = payload.get("repository", {}).get("html_url", f"https://github.com/{owner}/{repo_name}")
    default_branch = payload.get("repository", {}).get("default_branch", "main")

    incident = await create_incident(
        session=session,
        incident_id=incident_id,
        github_payload={
            **parsed.payload,
            "_recovery_metadata": {
                "event_name": parsed.event_name,
                "is_failure_event": (
                    parsed.is_failure_event
                ),
                "affected_files": list(
                    parsed.affected_files
                ),
                "github_run_id": parsed.github_run_id,
                "workflow_name": parsed.workflow_name,
            },
        },
        repository=parsed.repository,
        branch=extracted_branch,
        commit_sha=extracted_commit_sha,
        is_mock_mode=is_mock_mode,
        repository_owner=owner,
        repository_name=repo_name,
        repository_full_name=f"{owner}/{repo_name}",
        repository_url=repo_url,
        default_branch=default_branch,
        source_branch=extracted_branch,
        workflow_run_id=str(parsed.github_run_id or ""),
    )

    await record_audit_event(
        session=session,
        incident_uuid=incident.id,
        incident_id=incident.incident_id,
        event=AuditEventCreate(
            event_type=(
                AuditEventType.INCIDENT_CREATED.value
            ),
            message=(
                "Incident accepted and recovery graph "
                "scheduled."
            ),
            reasoning=(
                "GitHub signature was verified and the "
                "payload was normalized."
            ),
            event_metadata={
                "event_name": parsed.event_name,
                "repository": parsed.repository,
                "branch": parsed.branch,
                "commit_sha": parsed.commit_sha,
                "mock_mode": is_mock_mode,
                "github_run_id": parsed.github_run_id,
                "workflow_name": parsed.workflow_name,
            },
        ),
    )

    # Broadcast live typed events to SSE listeners: webhook -> incident_created
    await telemetry_manager.publish(
        incident_id=incident.incident_id,
        event_type="webhook",
        node_name="webhook_ingress",
        message=f"GitHub {parsed.event_name} webhook received for {parsed.repository}:{parsed.branch}",
        metadata={
            "event_name": parsed.event_name,
            "repository": parsed.repository,
            "branch": parsed.branch,
            "commit_sha": parsed.commit_sha,
            "github_run_id": parsed.github_run_id,
            "workflow_name": parsed.workflow_name,
        },
    )

    await telemetry_manager.publish(
        incident_id=incident.incident_id,
        event_type="incident_created",
        node_name="webhook_ingress",
        message=f"Incident {incident.incident_id} created for {parsed.repository}:{parsed.branch}",
        metadata={
            "incident_id": incident.incident_id,
            "repository": parsed.repository,
            "branch": parsed.branch,
            "commit_sha": parsed.commit_sha,
            "github_run_id": parsed.github_run_id,
            "workflow_name": parsed.workflow_name,
        },
    )

    await telemetry_manager.publish(
        incident_id=incident.incident_id,
        event_type="incident_detected",
        node_name="webhook_ingress",
        message=f"Incident detected from GitHub {parsed.event_name} event on {parsed.repository}:{parsed.branch}",
        metadata={
            "repository": parsed.repository,
            "branch": parsed.branch,
            "commit_sha": parsed.commit_sha,
            "github_run_id": parsed.github_run_id,
            "workflow_name": parsed.workflow_name,
        },
    )

    await session.commit()

    state = create_initial_recovery_state(
        incident_id=incident.incident_id,
        github_payload=incident.github_payload,
        is_mock_mode=incident.is_mock_mode,
    )
    state["repository_owner"] = incident.repository_owner
    state["repository_name"] = incident.repository_name
    state["repository_full_name"] = incident.repository_full_name
    state["repository_url"] = incident.repository_url
    state["default_branch"] = incident.default_branch
    state["source_branch"] = incident.source_branch
    state["commit_sha"] = incident.commit_sha or ""

    asyncio.create_task(
        recovery_runtime.run(state)
    )

    return {
        "accepted": True,
        "incident_id": incident.incident_id,
        "repository": incident.repository,
        "branch": incident.branch,
        "is_mock_mode": incident.is_mock_mode,
        "message": "Recovery incident accepted.",
    }
