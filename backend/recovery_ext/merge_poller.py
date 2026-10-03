"""
Poller to check GitHub PR merge status for incidents stuck in PR_OPEN state.
"""

import asyncio
import logging
import os
from sqlalchemy import select

from backend.db.session import AsyncSessionLocal
from backend.db.models import Incident, IncidentStatus
from backend.recovery_ext.flags import get_flags
from backend.recovery_ext.post_merge import trigger_post_merge_verification

logger = logging.getLogger(__name__)

async def merge_poller_task():
    interval = int(os.environ.get("MERGE_POLL_INTERVAL_SECONDS", "10"))
    while True:
        try:
            flags = get_flags()
            if not flags.enable_post_merge_verify:
                await asyncio.sleep(interval)
                continue
                
            from github import Github, Auth
            from backend.config import get_settings
            
            settings = get_settings()
            if not settings.github_token:
                await asyncio.sleep(interval)
                continue
                
            try:
                auth = Auth.Token(settings.github_token)
                gh = Github(auth=auth, timeout=10)
            except Exception:
                gh = Github(login_or_token=settings.github_token, timeout=10)
            
            async with AsyncSessionLocal() as session:
                stmt = select(Incident).where(
                    Incident.status == IncidentStatus.PR_OPEN,
                    Incident.pr_url != ""
                )
                result = await session.execute(stmt)
                incidents = result.scalars().all()
                
            for incident in incidents:
                if not incident.repository_full_name:
                    continue
                pr_url = incident.pr_url
                if "/pull/" not in pr_url:
                    continue
                pr_number = int(pr_url.split("/pull/")[-1].split("/")[0])
                
                loop = asyncio.get_event_loop()
                repo = await loop.run_in_executor(None, gh.get_repo, incident.repository_full_name)
                pr = await loop.run_in_executor(None, repo.get_pull, pr_number)
                
                if pr.is_merged():
                    logger.info(f"[POLLER] Detected merge for PR #{pr_number}")
                    await trigger_post_merge_verification(
                        incident_id=incident.incident_id,
                        pr_number=pr_number,
                        repository_full_name=incident.repository_full_name,
                        merged_sha=pr.merge_commit_sha,
                    )
                    
        except Exception as e:
            logger.error(f"[POLLER] Error: {e}")
            
        await asyncio.sleep(interval)

_poller_task = None

def start_merge_poller():
    global _poller_task
    if _poller_task is None:
        loop = asyncio.get_running_loop()
        _poller_task = loop.create_task(merge_poller_task())
