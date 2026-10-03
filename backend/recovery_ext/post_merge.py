"""
recovery_ext/post_merge.py
─────────────────────────
Phase 7: Post-Merge Verification & Drift Detection.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from backend.config import get_settings
from backend.db.session import AsyncSessionLocal
from backend.recovery_ext.flags import get_flags
from backend.orchestration.telemetry import emit_node_event
from backend.sandbox.sandbox import RecoverySandbox

logger = logging.getLogger(__name__)


async def trigger_post_merge_verification(
    incident_id: str,
    pr_number: int,
    repository_full_name: str,
    merged_sha: str,
) -> None:
    """
    Called when a PR merge is detected (either by auto-merge or webhook).
    """
    flags = get_flags()
    if not flags.enable_post_merge_verify:
        return

    # We need to emit the pr_merged event so the frontend updates immediately
    from backend.orchestration.telemetry import emit_node_event
    asyncio.create_task(emit_node_event(
        incident_id=incident_id,
        event_type="pr_merged",
        node_name="merge_detector",
        message=f"PR #{pr_number} merged (SHA: {merged_sha[:7]}). Starting post-merge verification.",
        metadata={"merge_sha": merged_sha, "pr_number": pr_number},
    ))
    
    # To avoid blocking the webhook or current request, run in background
    asyncio.create_task(_run_post_merge_verification(
        incident_id=incident_id,
        pr_number=pr_number,
        repository_full_name=repository_full_name,
        merged_sha=merged_sha,
    ))


async def _run_post_merge_verification(
    incident_id: str,
    pr_number: int,
    repository_full_name: str,
    merged_sha: str,
) -> None:
    logger.info(f"[POST_MERGE] Starting verification for incident {incident_id}, PR #{pr_number}")
    
    # 1. Fetch incident state from DB to get the original patch hash and files
    from sqlalchemy import select
    from backend.db.models import Incident
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Incident).where(Incident.incident_id == incident_id)
        )
        incident = result.scalars().first()
        if not incident:
            logger.error(f"[POST_MERGE] Incident {incident_id} not found")
            return
            
        test_results = incident.test_results or {}
        # Try to find the packager event to get the original patch hash
        # If not stored directly, we can hash the current_patch_diff
        # For simplicity, we assume we need to clone the repo, checkout the merged_sha,
        # run the tests, and hash the modified file.
        
    workspace: Path | None = None
    sandbox: RecoverySandbox | None = None
    
    try:
        settings = get_settings()
        token = settings.github_token
        if not token:
            logger.error("[POST_MERGE] No github token available")
            return
            
        # Clone repo
        repo_url = f"https://{token}@github.com/{repository_full_name}.git"
        recovery_dir = Path("/tmp/recovery")
        recovery_dir.mkdir(parents=True, exist_ok=True)
        workspace = Path(tempfile.mkdtemp(prefix=f"post-merge-{incident_id}-", dir=recovery_dir))
        
        # Git clone and checkout the merged commit
        import subprocess
        subprocess.run(["git", "clone", repo_url, str(workspace)], check=True, capture_output=True)
        subprocess.run(["git", "checkout", merged_sha], cwd=str(workspace), check=True, capture_output=True)
        
        # Get the actual state of the affected file(s)
        # For drift detection, we need to know what file was changed.
        # Let's get it from the incident state if possible, or just run tests.
        
        # Run tests in sandbox
        sandbox = RecoverySandbox()
        # We don't apply a patch here, we just run the tests on the already merged code!
        # The RecoverySandbox._run_tests_local or container can be used.
        # Let's use the container manually
        
        container = None
        exit_code = 1
        tests_passed = False
        
        from backend.recovery_ext.sandbox_policy import get_policy_kwargs
        try:
            policy_kwargs = get_policy_kwargs()
        except ImportError:
            policy_kwargs = {}
            
        if sandbox.use_docker and sandbox.client:
            base_kwargs = {
                "image": sandbox.settings.image,
                "command": ["sleep", "infinity"],
                "working_dir": sandbox.settings.working_directory,
                "network_mode": "none",
                "detach": True,
                "auto_remove": False,
                "mem_limit": sandbox.settings.memory_limit,
                "nano_cpus": int(sandbox.settings.cpu_limit * 1_000_000_000),
                "pids_limit": sandbox.settings.pids_limit,
                "read_only": False,
                "security_opt": ["no-new-privileges:true"],
                "cap_drop": ["ALL"],
                "volumes": {
                    str(workspace): {
                        "bind": sandbox.settings.working_directory,
                        "mode": "rw",
                    }
                },
            }
            labels = policy_kwargs.pop("labels", {})
            base_kwargs["labels"] = labels
            base_kwargs.update(policy_kwargs)
            
            container = sandbox.client.containers.create(**base_kwargs)
            container.start()
            
            test_res = sandbox._exec(
                container,
                ["python", "-m", "pytest", "-q", "--disable-warnings", "--maxfail=1"],
                timeout_seconds=sandbox.settings.pytest_timeout_seconds,
            )
            exit_code = test_res.exit_code
            tests_passed = (exit_code == 0 and not test_res.timed_out)
        else:
            # Fallback to local
            test_res = sandbox._run_local_command(
                ["python", "-m", "pytest", "-q", "--disable-warnings", "--maxfail=1"],
                cwd=workspace,
                timeout_seconds=sandbox.settings.pytest_timeout_seconds,
            )
            exit_code = test_res.exit_code
            tests_passed = (exit_code == 0 and not test_res.timed_out)
            
        # Drift Detection: Did the tests fail?
        # A simple drift definition: if tests failed after merge, it's drift or conflicting changes.
        drift_detected = not tests_passed
        
        final_status = "DRIFT_DETECTED" if drift_detected else "VERIFIED_POST_MERGE"
        
        await emit_node_event(
            incident_id=incident_id,
            event_type="post_merge_verify",
            node_name="post_merge",
            message=f"[POST_MERGE_VERIFY] Tests {'passed ✓' if tests_passed else 'failed ✗'}",
            metadata={
                "exit_code": exit_code,
                "tests_passed": tests_passed,
                "merged_sha": merged_sha,
                "stage": "post_merge",
            },
            retry_count=0,
        )
        
        if drift_detected:
            await emit_node_event(
                incident_id=incident_id,
                event_type="drift_detected",
                node_name="post_merge",
                message=f"[DRIFT_DETECTION] Code drift detected on main branch after merge. Tests failed.",
                metadata={
                    "drift": True,
                    "merged_sha": merged_sha,
                    "stage": "post_merge",
                },
                retry_count=0,
            )
            
        # Update incident status
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Incident).where(Incident.incident_id == incident_id)
            )
            inc = result.scalars().first()
            if inc:
                inc.status = final_status
                await session.commit()
                
        # Optional: reopen if auto-reopen is enabled
        auto_reopen = os.environ.get("AUTO_REOPEN_ON_DRIFT", "false").lower() in ("true", "1")
        if drift_detected and auto_reopen:
            # Max reopen guard: check if this is already a reopened incident (e.g. incident_id contains '-reopen')
            if "-reopen" not in incident_id:
                logger.info(f"[POST_MERGE] Auto-reopening incident {incident_id} due to drift")
                # Trigger a new incident creation (out of scope for this simple file, but could call event_bridge)
                pass
                
    except Exception as e:
        logger.error(f"[POST_MERGE] Verification failed: {e}")
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Incident).where(Incident.incident_id == incident_id)
            )
            inc = result.scalars().first()
            if inc:
                inc.status = "POST_MERGE_FAILED"
                await session.commit()
    finally:
        # Cleanup
        try:
            from backend.recovery_ext.scavenger import run_scavenger
            await run_scavenger(
                incident_id=incident_id,
                container=container if 'container' in locals() else None,
                workspace=workspace,
            )
        except Exception:
            pass


async def start_bounded_poller(
    incident_id: str,
    pr_number: int,
    repository_full_name: str,
    max_attempts: int = 10,
    backoff_seconds: int = 5,
) -> None:
    """
    Polls GitHub for the PR merge status if Webhooks are not configured.
    """
    flags = get_flags()
    if not flags.enable_post_merge_verify:
        return
        
    asyncio.create_task(_poll_for_merge(
        incident_id=incident_id,
        pr_number=pr_number,
        repository_full_name=repository_full_name,
        max_attempts=max_attempts,
        backoff_seconds=backoff_seconds,
    ))

async def _poll_for_merge(
    incident_id: str,
    pr_number: int,
    repository_full_name: str,
    max_attempts: int,
    backoff_seconds: int,
) -> None:
    from github import Github, Auth
    settings = get_settings()
    if not settings.github_token:
        return
        
    try:
        auth = Auth.Token(settings.github_token)
        gh = Github(auth=auth, timeout=10)
    except Exception:
        gh = Github(login_or_token=settings.github_token, timeout=10)
        
    for attempt in range(max_attempts):
        try:
            # We must use run_in_executor since PyGithub is sync
            loop = asyncio.get_event_loop()
            repo = await loop.run_in_executor(None, gh.get_repo, repository_full_name)
            pr = await loop.run_in_executor(None, repo.get_pull, pr_number)
            
            if pr.is_merged():
                logger.info(f"[POST_MERGE] Poller detected merge for PR #{pr_number}")
                await trigger_post_merge_verification(
                    incident_id=incident_id,
                    pr_number=pr_number,
                    repository_full_name=repository_full_name,
                    merged_sha=pr.merge_commit_sha,
                )
                return
                
        except Exception as e:
            logger.warning(f"[POST_MERGE] Poller error on attempt {attempt+1}: {e}")
            
        await asyncio.sleep(backoff_seconds)
        
    logger.info(f"[POST_MERGE] Poller timed out after {max_attempts} attempts for PR #{pr_number}")
