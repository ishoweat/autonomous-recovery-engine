import asyncio
import logging
import uuid
from typing import Any

from backend.db.session import AsyncSessionLocal
from backend.services.incidents import create_incident
from backend.orchestration.state_factory import create_initial_recovery_state
from backend.orchestration.runtime import recovery_runtime
from backend.recovery_ext.flags import get_flags

logger = logging.getLogger(__name__)

# Queue for validated webhooks
webhook_queue = asyncio.Queue(maxsize=100)
_worker_task: asyncio.Task | None = None

async def _process_webhook_event(item: dict[str, Any]):
    payload = item.get("payload", {})
    workflow_run = payload.get("workflow_run", {})
    repo_data = payload.get("repository", {})
    owner_data = repo_data.get("owner", {})
    
    owner = owner_data.get("login")
    repo = repo_data.get("name")
    full_name = repo_data.get("full_name")
    repository_url = repo_data.get("html_url")
    default_branch = repo_data.get("default_branch", "main")
    
    if "pull_request" in payload:
        # Phase 7: Post-merge verification trigger
        pr = payload.get("pull_request", {})
        merged_sha = pr.get("merge_commit_sha")
        pr_number = pr.get("number")
        
        # We need to find the incident_id associated with this PR.
        # This can be found in the database.
        from sqlalchemy import select
        from backend.db.models import Incident
        
        async with AsyncSessionLocal() as session:
            # We search for the incident that has this pr_url or pr_number.
            # In a real app we'd index this, but for the demo this is sufficient.
            pr_url = pr.get("html_url", "")
            result = await session.execute(
                select(Incident).where(Incident.pr_url == pr_url)
            )
            incident = result.scalars().first()
            if incident:
                from backend.recovery_ext.post_merge import trigger_post_merge_verification
                await trigger_post_merge_verification(
                    incident_id=incident.incident_id,
                    pr_number=pr_number,
                    repository_full_name=full_name,
                    merged_sha=merged_sha,
                )
            else:
                logger.info(f"No active incident found for merged PR {pr_url}")
        return

    commit_sha = workflow_run.get("head_sha", "unknown")
    detected_branch = workflow_run.get("head_branch", default_branch)
    workflow_name = workflow_run.get("name", "unknown")
    run_id = workflow_run.get("id")
    
    # Fetch job logs via PyGithub
    from backend.config.github_config import get_github_settings
    from backend.integrations.github_tools import GitHubTools
    gh_tools = GitHubTools(get_github_settings())
    log_data = {"stack_trace": "", "failure_file": "", "error_message": ""}
    if run_id:
        try:
            log_data = gh_tools.get_workflow_run_logs_and_traceback(full_name, int(run_id))
        except Exception as e:
            logger.error(f"Failed to fetch logs for run {run_id}: {e}")
    
    incident_id = f"inc_{uuid.uuid4().hex}"
    
    async with AsyncSessionLocal() as session:
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
                    "conclusion": workflow_run.get("conclusion"),
                    "id": run_id,
                    "html_url": workflow_run.get("html_url"),
                    "trigger": "Webhook", # Optional extra field per requirements
                    "delivery_id": item.get("delivery_id")
                },
                "stack_trace": log_data.get("stack_trace"),
                "failure_file": log_data.get("failure_file"),
                "error_message": log_data.get("error_message"),
            },
            repository=full_name,
            repository_owner=owner,
            repository_name=repo,
            repository_full_name=full_name,
            repository_url=repository_url,
            default_branch=default_branch,
            branch=detected_branch,
            commit_sha=commit_sha,
            is_mock_mode=False,
            # System driven, no user context
            user_id=None,
            username="github-webhook",
            session_id=None,
        )
        await session.commit()
        
        state = create_initial_recovery_state(
            incident_id=incident.incident_id,
            github_payload=incident.github_payload,
            is_mock_mode=False,
            repository_owner=owner,
            repository_name=repo,
            repository_full_name=full_name,
            repository_url=repository_url,
            default_branch=default_branch,
            source_branch=detected_branch,
            commit_sha=commit_sha,
            user_id="",
            username="github-webhook",
            session_id="",
            user_oauth_token="", # Usually depends on app installation token logic, which is handled elsewhere or uses settings.github_token
        )
        
        # Start existing pipeline
        asyncio.create_task(recovery_runtime.run(state))
        logger.info(f"Started pipeline for incident {incident_id} triggered via webhook")


async def _webhook_worker():
    while True:
        try:
            item = await webhook_queue.get()
            try:
                await _process_webhook_event(item)
            except Exception as e:
                logger.error(f"Error processing webhook event: {e}")
            finally:
                webhook_queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Webhook worker encountered an error: {e}")

async def start_webhook_worker():
    global _worker_task
    flags = get_flags()
    if flags.enable_webhook_ingress and _worker_task is None:
        loop = asyncio.get_running_loop()
        _worker_task = loop.create_task(_webhook_worker())

async def stop_webhook_worker():
    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
