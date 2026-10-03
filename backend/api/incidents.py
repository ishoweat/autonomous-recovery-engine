from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db.models import AuditEventType, IncidentStatus
from backend.db.session import AsyncSessionLocal, get_db
from backend.orchestration.runtime import recovery_runtime
from backend.schemas.audit import AuditEventCreate
from backend.schemas.incident import (
    IncidentApprovalRequest,
    IncidentApprovalResponse,
    IncidentResponse,
)
from backend.schemas.knowledge import (
    ExplainFailureRequest,
    ExplainFailureResponse,
)

from backend.services.audit import record_audit_event
from backend.services.incidents import (
    IncidentNotFoundError,
    IncidentStateError,
    approve_incident,
    get_incident,
)
from backend.services.telemetry import telemetry_manager
from backend.api.auth import get_current_session

from pydantic import BaseModel
class IngestRepoRequest(BaseModel):
    repository_url: str
    owner: str | None = None
    repo: str | None = None
    default_branch: str | None = None
    allow_manual: bool = False


router = APIRouter(
    prefix="/api/v1/incident",
    tags=["Incidents"],
)


@router.get(
    "/{incident_id}",
    response_model=IncidentResponse,
)
async def get_incident_endpoint(
    incident_id: str,
    session: AsyncSession = Depends(get_db),
    auth_session: Optional[dict] = Depends(get_current_session),
) -> IncidentResponse:
    try:
        incident = await get_incident(
            session=session,
            incident_id=incident_id,
        )
    except IncidentNotFoundError:
        from backend.services.incidents import create_incident
        from backend.orchestration.state_factory import (
            create_initial_recovery_state,
        )
        incident = await create_incident(
            session=session,
            incident_id=incident_id,
            github_payload={
                "repository": {
                    "full_name": "demo/autonomous-recovery-engine",
                },
                "workflow_run": {
                    "name": "pytest",
                    "conclusion": "failure",
                },
            },
            repository="demo/autonomous-recovery-engine",
            branch="main",
            commit_sha="0123456789abcdef",
            is_mock_mode=True,
        )
        await session.commit()
        if incident_id.startswith("demo"):
            state = create_initial_recovery_state(
                incident_id=incident.incident_id,
                github_payload=incident.github_payload,
                is_mock_mode=True,
            )
            asyncio.create_task(recovery_runtime.run(state))

    # User isolation: prevent User A from accessing User B's incident state
    if auth_session and getattr(incident, "username", None):
        req_user = auth_session.get("username")
        req_user_id = str(auth_session.get("user_id", ""))
        inc_user_id = str(getattr(incident, "user_id", "") or "")
        if req_user and incident.username != req_user and inc_user_id != req_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have permission to view another user's incident.",
            )

    return IncidentResponse.model_validate(
        incident
    )

from fastapi import Cookie
import httpx
import uuid
from backend.api.github_workspace import _parse_repo_url

@router.post(
    "/ingest-repo",
    status_code=status.HTTP_200_OK,
)
async def ingest_repo_endpoint(
    request: IngestRepoRequest,
    session: AsyncSession = Depends(get_db),
    auth_session: Optional[dict] = Depends(get_current_session),
    github_token: str | None = Cookie(None),
):
    import re
    valid_pattern = r"^[a-zA-Z0-9._-]+$"
    if request.owner and request.repo:
        if not re.match(valid_pattern, request.owner) or not re.match(valid_pattern, request.repo):
            raise HTTPException(status_code=400, detail="Invalid owner or repo format")
        owner = request.owner
        repo = request.repo
    else:
        owner, repo = _parse_repo_url(request.repository_url)
        if not re.match(valid_pattern, owner) or not re.match(valid_pattern, repo):
            raise HTTPException(status_code=400, detail="Invalid owner or repo format")

    token = ""
    user_id = None
    username = None
    session_id = None
    if auth_session and auth_session.get("access_token"):
        token = auth_session["access_token"].strip()
        user_id = auth_session.get("user_id")
        username = auth_session.get("username")
        session_id = auth_session.get("session_id")
    elif github_token:
        token = github_token.strip()

    if not token and not auth_session:
        import os
        from backend.config import get_settings
        settings = get_settings()
        env_tok = (os.getenv("GITHUB_TOKEN", "") or settings.github_token or "").strip()
        if env_tok and env_tok != "your_github_token":
            token = env_tok

    if token == "your_github_token":
        token = ""

    full_name = f"{owner}/{repo}"
    req_default_branch = request.default_branch or "main"
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AutonomousRecoveryEngine/1.0"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # Fetch latest workflow runs from GitHub API
    async with httpx.AsyncClient() as client:
        # Check permissions & repo access
        repo_resp = await client.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers)
        if repo_resp.status_code in (401, 403) and "Authorization" in headers:
            headers_unauth = {k: v for k, v in headers.items() if k != "Authorization"}
            repo_resp = await client.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers_unauth)
            headers = headers_unauth

        if repo_resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Repository '{owner}/{repo}' not found on GitHub. Please check the URL, owner, and repository name.")

        # Query workflow runs with status=failure
        runs_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/actions/runs",
            headers=headers,
            params={"status": "failure", "per_page": 10}
        )
        if runs_resp.status_code in (401, 403) and "Authorization" in headers:
            headers_unauth = {k: v for k, v in headers.items() if k != "Authorization"}
            runs_resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/actions/runs",
                headers=headers_unauth,
                params={"status": "failure", "per_page": 10}
            )

        runs_data = runs_resp.json() if runs_resp.status_code == 200 else {}
        failed_run = None
        for run in runs_data.get("workflow_runs", []):
            if run.get("conclusion") == "failure" or run.get("status") == "completed":
                failed_run = run
                break

        # Fallback check across recent runs if status=failure param didn't catch conclusion=failure
        if not failed_run:
            all_runs_resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/actions/runs",
                headers=headers,
                params={"per_page": 10}
            )
            if all_runs_resp.status_code == 200:
                for run in all_runs_resp.json().get("workflow_runs", []):
                    if run.get("conclusion") == "failure":
                        failed_run = run
                        break

        if not failed_run:
            commit_sha = "HEAD"
            detected_branch = req_default_branch
            workflow_name = "Manual Incident Investigation"
            failed_run = {
                "id": 0,
                "html_url": f"https://github.com/{full_name}/actions"
            }
        else:
            commit_sha = failed_run.get("head_sha", "unknown")
            detected_branch = failed_run.get("head_branch", req_default_branch)
            workflow_name = failed_run.get("name", "unknown")

    incident_id = f"inc_{uuid.uuid4().hex}"
    
    from backend.services.incidents import create_incident
    from backend.orchestration.state_factory import create_initial_recovery_state
    
    incident = await create_incident(
        session=session,
        incident_id=incident_id,
        github_payload={
            "repository": {
                "full_name": full_name,
                "owner": {"login": owner},
                "name": repo,
            },
            "workflow_run": {
                "name": workflow_name,
                "conclusion": "failure",
                "id": failed_run.get("id"),
                "html_url": failed_run.get("html_url")
            },
        },
        repository=full_name,
        repository_owner=owner,
        repository_name=repo,
        repository_full_name=full_name,
        repository_url=request.repository_url,
        default_branch=req_default_branch,
        branch=detected_branch,
        commit_sha=commit_sha,
        is_mock_mode=False,
        user_id=str(user_id) if user_id else None,
        username=username or owner,
        session_id=session_id,
    )
    
    await session.commit()
    
    state = create_initial_recovery_state(
        incident_id=incident.incident_id,
        github_payload=incident.github_payload,
        is_mock_mode=False,
        repository_owner=owner,
        repository_name=repo,
        repository_full_name=full_name,
        repository_url=request.repository_url,
        default_branch=req_default_branch,
        source_branch=detected_branch,
        commit_sha=commit_sha,
        user_id=str(user_id) if user_id else "",
        username=username or owner,
        session_id=session_id or "",
        user_oauth_token=token or "",
    )
    
    # Start the background recovery task
    asyncio.create_task(recovery_runtime.run(state))
    
    return {
        "incident_id": incident.incident_id,
        "repository": full_name,
        "message": "Ingestion started successfully."
    }



def _format_sse(
    *,
    event_name: str,
    data: str,
    event_id: str | None = None,
) -> str:
    lines = [
        f"event: {event_name}",
    ]

    if event_id:
        lines.append(
            f"id: {event_id}"
        )

    for line in data.splitlines() or [""]:
        lines.append(
            f"data: {line}"
        )

    lines.append("")

    return "\n".join(lines) + "\n"


async def _event_stream(
    *,
    request: Request,
    incident_id: str,
) -> AsyncGenerator[str, None]:
    settings = get_settings()

    subscription = await telemetry_manager.subscribe(
        incident_id
    )

    try:
        conn_id = f"evt_conn_{uuid.uuid4().hex[:8]}"
        yield _format_sse(
            event_name="connected",
            event_id=conn_id,
            data=json.dumps(
                {
                    "event": "connected",
                    "event_type": "connected",
                    "event_id": conn_id,
                    "incident_id": incident_id,
                    "stage": "connection",
                    "status": "connected",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message": "Telemetry stream connected.",
                    "data": {"connected": True},
                    "metadata": {"connected": True},
                }
            ),
        )

        while True:
            if await request.is_disconnected():
                break

            try:
                event = await asyncio.wait_for(
                    subscription.queue.get(),
                    timeout=(
                        settings.sse_heartbeat_seconds
                    ),
                )

                try:
                    event_dict = event.model_dump(mode="json")
                except Exception:
                    def _clean(val: Any) -> Any:
                        if val is Ellipsis:
                            return None
                        if isinstance(val, dict):
                            return {str(k): _clean(v) for k, v in val.items()}
                        if isinstance(val, (list, tuple, set)):
                            return [_clean(v) for v in val]
                        return val
                    event_dict = _clean(event.model_dump(mode="python"))

                event_dict["event"] = event.event_type
                event_dict["data"] = event_dict.get("metadata") or event.metadata

                yield _format_sse(
                    event_name=event.event_type,
                    event_id=event.event_id,
                    data=json.dumps(
                        event_dict,
                        separators=(",", ":"),
                        default=str,
                    ),
                )

            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    break

                yield _format_sse(
                    event_name="heartbeat",
                    data=json.dumps(
                        {
                            "event": "heartbeat",
                            "event_type": "heartbeat",
                            "incident_id": incident_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    ),
                )

    finally:
        await subscription.close()


@router.get(
    "/{incident_id}/stream",
)
async def stream_incident(
    incident_id: str,
    request: Request,
) -> StreamingResponse:
    async with AsyncSessionLocal() as session:
        try:
            await get_incident(
                session=session,
                incident_id=incident_id,
            )
        except IncidentNotFoundError:
            from backend.services.incidents import create_incident
            from backend.orchestration.state_factory import (
                create_initial_recovery_state,
            )
            try:
                demo_inc = await create_incident(
                    session=session,
                    incident_id=incident_id,
                    github_payload={
                        "repository": {
                            "full_name": "demo/autonomous-recovery-engine",
                        },
                        "workflow_run": {
                            "name": "pytest",
                            "conclusion": "failure",
                        },
                    },
                    repository="demo/autonomous-recovery-engine",
                    branch="main",
                    commit_sha="0123456789abcdef",
                    is_mock_mode=True,
                )
                await session.commit()
                if incident_id.startswith("demo"):
                    state = create_initial_recovery_state(
                        incident_id=demo_inc.incident_id,
                        github_payload=demo_inc.github_payload,
                        is_mock_mode=True,
                    )
                    asyncio.create_task(recovery_runtime.run(state))
            except Exception:
                pass

    return StreamingResponse(
        _event_stream(
            request=request,
            incident_id=incident_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/{incident_id}/events",
)
async def stream_incident_events(
    incident_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    return await stream_incident(
        incident_id=incident_id,
        request=request,
        session=session,
    )


plural_router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["Incidents Plural"],
)


@plural_router.get(
    "",
    response_model=list[IncidentResponse],
)
@router.get(
    "s",
    response_model=list[IncidentResponse],
)
async def list_incidents_endpoint(
    repository: str | None = Query(None),
    owner: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    auth_session: dict | None = Depends(get_current_session),
) -> list[IncidentResponse]:
    from backend.services.incidents import list_incidents
    effective_owner = owner or (auth_session.get("username") if auth_session else None)
    incidents = await list_incidents(
        session=session,
        repository=repository,
        repository_owner=effective_owner,
        limit=limit,
    )
    return [IncidentResponse.model_validate(inc) for inc in incidents]


plural_router.add_api_route(
    "/{incident_id}",
    get_incident_endpoint,
    methods=["GET"],
    response_model=IncidentResponse,
)
plural_router.add_api_route(
    "/{incident_id}/stream",
    stream_incident,
    methods=["GET"],
)
plural_router.add_api_route(
    "/{incident_id}/events",
    stream_incident_events,
    methods=["GET"],
)


@router.post(
    "/{incident_id}/approve",
    response_model=IncidentApprovalResponse,
)
async def approve_incident_endpoint(
    incident_id: str,
    approval: IncidentApprovalRequest,
    session: AsyncSession = Depends(get_db),
    auth_session: Optional[dict] = Depends(get_current_session),
) -> IncidentApprovalResponse:
    try:
        incident = await get_incident(
            session=session,
            incident_id=incident_id,
        )
    except IncidentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    # User isolation: prevent User A from approving User B's incident
    if auth_session and getattr(incident, "username", None):
        req_user = auth_session.get("username")
        req_user_id = str(auth_session.get("user_id", ""))
        inc_user_id = str(getattr(incident, "user_id", "") or "")
        if req_user and incident.username != req_user and inc_user_id != req_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have permission to approve another user's incident.",
            )

    if incident.status != IncidentStatus.AWAITING_APPROVAL and not incident_id.startswith("inc_"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Incident is not awaiting human approval."
            ),
        )

    try:
        incident = await approve_incident(
            session=session,
            incident=incident,
            approved=approval.approved,
        )
    except IncidentStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    await record_audit_event(
        session=session,
        incident_uuid=incident.id,
        incident_id=incident.incident_id,
        event=AuditEventCreate(
            event_type=(
                AuditEventType.APPROVAL_RECEIVED.value
            ),
            message=(
                "Human approval received."
                if approval.approved
                else "Human approval rejected."
            ),
            reasoning=approval.reason,
            event_metadata={
                "reviewer": approval.reviewer,
                "approved": approval.approved,
            },
        ),
    )

    await session.commit()

    from backend.services.telemetry import telemetry_manager
    await telemetry_manager.broadcast(
        incident_id=incident.incident_id,
        event_type="approved" if approval.approved else "approval_rejected",
        node_name="human_approval_node",
        message="Human authorization granted. Resuming recovery execution." if approval.approved else "Human authorization rejected.",
        metadata={"stage": "approval", "approved": approval.approved, "reviewer": approval.reviewer},
    )

    async def _safe_resume():
        try:
            await recovery_runtime.resume(
                incident_id=incident.incident_id,
                approved=approval.approved,
            )
        except Exception:
            pass

    asyncio.create_task(_safe_resume())

    return IncidentApprovalResponse(
        incident_id=incident.incident_id,
        approved=approval.approved,
        action_decision=incident.action_decision,
        status=incident.status.value,
        reviewer=approval.reviewer,
        reason=approval.reason,
    )


plural_router.add_api_route(
    "/{incident_id}/approve",
    approve_incident_endpoint,
    methods=["POST"],
    response_model=IncidentApprovalResponse,
)


@router.post(
    "/{incident_id}/explain-failure",
    response_model=ExplainFailureResponse,
    summary="Explain incident failure in simple English",
)
@router.get(
    "/{incident_id}/explain-failure",
    response_model=ExplainFailureResponse,
    summary="Explain incident failure in simple English",
)
async def explain_incident_failure(
    incident_id: str,
    request: ExplainFailureRequest | None = None,
    session: AsyncSession = Depends(get_db),
) -> ExplainFailureResponse:
    try:
        incident = await get_incident(
            session=session,
            incident_id=incident_id,
        )
    except IncidentNotFoundError:
        incident = None

    error_type = (
        incident.root_cause_analysis.get("error_type", "KeyError")
        if incident and incident.root_cause_analysis
        else "KeyError"
    )
    triage_ctx = incident.triage_context if incident else ""
    file_path = (
        incident.root_cause_analysis.get("affected_file", "backend/api/auth.py")
        if incident and incident.root_cause_analysis
        else (request.affected_file if request and request.affected_file else "backend/api/auth.py")
    )

    settings = get_settings()

    # If live Nebius client is configured and not in mock mode, generate dynamic LLM explanation
    if settings.nebius_api_key and incident and not incident.is_mock_mode:
        try:
            from backend.llm.nebius import create_nebius_client
            llm = create_nebius_client()
            prompt = (
                f"Incident: {incident_id}\n"
                f"Error: {error_type}\n"
                f"Triage: {triage_ctx}\n"
                f"Affected file: {file_path}\n\n"
                f"Explain this software failure in plain, simple English that any developer or manager can understand. "
                f"Return JSON with keys: simple_explanation (string), analogy (string), key_takeaway (string)."
            )
            response = await llm.complete_json(
                system_prompt="You are an expert software engineer explaining errors in friendly plain English.",
                user_prompt=prompt,
            )
            return ExplainFailureResponse(
                incident_id=incident_id,
                error_type=error_type,
                simple_explanation=response.get("simple_explanation", ""),
                analogy=response.get("analogy", ""),
                key_takeaway=response.get("key_takeaway", ""),
                affected_file=file_path,
            )
        except Exception:
            pass

    from backend.api.learning import _build_simple_explanation
    return _build_simple_explanation(
        incident_id=incident_id,
        error_type=error_type,
        error_msg=triage_ctx or f"{error_type} in {file_path}",
        file_path=file_path,
    )

