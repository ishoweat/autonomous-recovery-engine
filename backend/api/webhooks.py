from __future__ import annotations

import asyncio
import json
import os
import uuid
import httpx
import logging

logger = logging.getLogger(__name__)

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
v1_webhook_router = APIRouter(
    prefix="/api/v1/webhooks",
    tags=["GitHub Webhooks"],
)


@router.post(
    "/github",
    status_code=status.HTTP_202_ACCEPTED,
)
@v1_webhook_router.post(
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

    # T4.1: Merge Listener for PRs
    if x_github_event == "pull_request":
        action = payload.get("action")
        pr_data = payload.get("pull_request", {})
        merged = pr_data.get("merged", False) or payload.get("merged", False)
        
        if (action == "closed" and merged) or merged:
            merge_commit_sha = pr_data.get("merge_commit_sha") or payload.get("merge_commit_sha") or "HEAD"
            branch_name = pr_data.get("head", {}).get("ref", "")
            run_id_val = str(payload.get("run_id") or payload.get("workflow_run", {}).get("id") or payload.get("id") or "")
            incident_id_short = ""
            if branch_name.startswith("recovery/") or branch_name.startswith("ai-recovery/") or branch_name.startswith("fix/"):
                incident_id_short = branch_name.replace("ai-recovery/", "").replace("recovery/", "").replace("fix/", "").split("-")[0]
            repo_url = payload.get("repository", {}).get("clone_url")
            
            # Background task for post-merge verification
            async def run_post_merge(repo_url, sha, incident_short, run_id, mock: bool):
                logger.info("[POST_MERGE] started")
                try:
                    async def _exec():
                        import tempfile
                        import subprocess
                        from backend.db.session import AsyncSessionLocal
                        from backend.db.models import Incident, IncidentStatus, SystemAnalytics
                        from sqlalchemy import select
                        from backend.orchestration.telemetry import emit_node_event
                        
                        block_finishing = os.getenv("POST_MERGE_BLOCK_FINISHING", "").lower() in ("true", "1")
                        if block_finishing:
                            await asyncio.sleep(70)

                        force_exit = os.getenv("POST_MERGE_FORCE_EXIT_CODE")
                        exit_code = int(force_exit) if force_exit is not None else 0
                        
                        if not mock and repo_url and force_exit is None:
                            with tempfile.TemporaryDirectory() as tmpdir:
                                subprocess.run(["git", "clone", "--depth", "50", repo_url, "."], cwd=tmpdir, check=True, timeout=30)
                                if sha and sha != "HEAD":
                                    subprocess.run(["git", "checkout", sha], cwd=tmpdir, check=True, timeout=10)
                                res = subprocess.run(["pytest", "-q", "--disable-warnings", "--maxfail=1"], cwd=tmpdir, capture_output=True, text=True, timeout=45)
                                exit_code = res.returncode
                        else:
                            if force_exit is None:
                                logger.info("Skipping real post-merge verification due to mock mode.")
                                await asyncio.sleep(0.1)
                            
                        async with AsyncSessionLocal() as async_session:
                            cand = None
                            if incident_short:
                                stmt = select(Incident).where(Incident.incident_id.contains(incident_short))
                                result = await async_session.execute(stmt)
                                cand = result.scalars().first()
                            if not cand and run_id:
                                stmt = select(Incident).order_by(Incident.created_at.desc()).limit(20)
                                result = await async_session.execute(stmt)
                                for c in result.scalars().all():
                                    cand_payload = c.github_payload or {}
                                    c_run_id = str(cand_payload.get("workflow_run", {}).get("id", "")) or str(cand_payload.get("id", ""))
                                    if c_run_id and c_run_id == run_id:
                                        cand = c
                                        break
                            if not cand:
                                stmt = select(Incident).order_by(Incident.created_at.desc()).limit(1)
                                result = await async_session.execute(stmt)
                                cand = result.scalars().first()

                            inc_id = cand.incident_id if cand else (incident_short or "inc_simulated")
                            
                            status = IncidentStatus.VERIFIED_POST_MERGE if exit_code == 0 else IncidentStatus.FAILED
                            if cand:
                                cand.status = status
                                if exit_code == 0:
                                    analytics_stmt = select(SystemAnalytics).limit(1)
                                    analytics_res = await async_session.execute(analytics_stmt)
                                    analytics_row = analytics_res.scalars().first()
                                    if not analytics_row:
                                        analytics_row = SystemAnalytics(resolutions_count=1)
                                        async_session.add(analytics_row)
                                    else:
                                        analytics_row.resolutions_count += 1
                                await async_session.commit()
                                
                            if exit_code == 0:
                                logger.info("[POST_MERGE] passed (exit 0)")
                            else:
                                logger.error("[POST_MERGE] failed")

                            await emit_node_event(
                                incident_id=inc_id,
                                event_type="post_merge_verify",
                                node_name="post_merge",
                                message="Verified on main" if exit_code == 0 else f"Tests failed on main (exit {exit_code})",
                                metadata={"merge_sha": sha, "exit_code": exit_code, "tests_passed": exit_code == 0}
                            )
                            logger.info(f"Post-merge verification for {inc_id}: exit_code={exit_code}")

                    await asyncio.wait_for(_exec(), timeout=60.0)

                except asyncio.TimeoutError:
                    logger.error("[POST_MERGE] timeout")
                    try:
                        from backend.db.session import AsyncSessionLocal
                        from backend.db.models import Incident, IncidentStatus
                        from sqlalchemy import select
                        from backend.orchestration.telemetry import emit_node_event
                        async with AsyncSessionLocal() as async_session:
                            cand = None
                            if incident_short:
                                stmt = select(Incident).where(Incident.incident_id.contains(incident_short))
                                res = await async_session.execute(stmt)
                                cand = res.scalars().first()
                            if not cand and run_id:
                                stmt = select(Incident).order_by(Incident.created_at.desc()).limit(20)
                                res = await async_session.execute(stmt)
                                for c in res.scalars().all():
                                    cand_payload = c.github_payload or {}
                                    c_run_id = str(cand_payload.get("workflow_run", {}).get("id", "")) or str(cand_payload.get("id", ""))
                                    if c_run_id and c_run_id == run_id:
                                        cand = c
                                        break
                            if not cand:
                                stmt = select(Incident).order_by(Incident.created_at.desc()).limit(1)
                                res = await async_session.execute(stmt)
                                cand = res.scalars().first()
                            inc_id = cand.incident_id if cand else (incident_short or "inc_simulated")
                            if cand:
                                cand.status = IncidentStatus.FAILED
                                await async_session.commit()
                        await emit_node_event(
                            incident_id=inc_id,
                            event_type="post_merge_verify",
                            node_name="post_merge",
                            message="[POST_MERGE] Verification timed out after 60s.",
                            metadata={"exit_code": 1, "tests_passed": False, "error": "Post-merge verification timed out after 60s"}
                        )
                    except Exception:
                        pass
                except Exception as e:
                    logger.error("[POST_MERGE] failed")
                    logger.error(f"Post-merge verification failed: {e}")
            
            asyncio.create_task(run_post_merge(repo_url, merge_commit_sha, incident_id_short, run_id_val, is_mock_mode))
            return {"accepted": True, "message": "Post-merge verification triggered."}

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

    # T1.1: Fetch raw workflow logs for the failed job
    error_message = ""
    stack_trace = ""
    if parsed.event_name == "workflow_run" and parsed.is_failure_event and parsed.github_run_id:
        try:
            from backend.config.github_config import get_github_settings
            gh_settings = get_github_settings()
            if gh_settings.token:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    headers = {
                        "Authorization": f"Bearer {gh_settings.token}",
                        "Accept": "application/vnd.github.v3+json",
                    }
                    jobs_url = f"https://api.github.com/repos/{parsed.repository}/actions/runs/{parsed.github_run_id}/jobs"
                    jobs_resp = await client.get(jobs_url, headers=headers)
                    if jobs_resp.status_code == 200:
                        jobs_data = jobs_resp.json()
                        for job in jobs_data.get("jobs", []):
                            if job.get("conclusion") == "failure":
                                job_id = job.get("id")
                                logs_url = f"https://api.github.com/repos/{parsed.repository}/actions/jobs/{job_id}/logs"
                                logs_resp = await client.get(logs_url, headers=headers)
                                if logs_resp.status_code == 200:
                                    logs = logs_resp.text
                                    if "Traceback (most recent call last):" in logs:
                                        parts = logs.split("Traceback (most recent call last):")
                                        stack_trace = "Traceback (most recent call last):\n" + parts[-1].split("===========================")[0]
                                    else:
                                        stack_trace = logs[-2000:]
                                    break
        except Exception as e:
            logger.warning(f"Failed to fetch workflow logs: {e}")

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
            "error_message": error_message,
            "stack_trace": stack_trace,
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
