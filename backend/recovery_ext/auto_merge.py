"""
recovery_ext/auto_merge.py
──────────────────────────
Phase 6: Auto-merge step (only when ENABLE_AUTO_MERGE=true).

Rules:
  - Only merges PRs on the ALLOW decision path (automated, no human required).
  - NEVER auto-merges APPROVE-path PRs unless operator explicitly approved them.
  - Uses squash merge with a clear, traceable commit message.
  - Respects branch protection: if the merge API returns 405/422 it reports
    the refusal and leaves the PR open (no silent failure).
  - Emits [AUTO_MERGE] telemetry events.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AutoMergeResult:
    merged: bool
    method: str             # "squash" | "skipped" | "refused" | "error"
    pr_url: str
    pr_number: int
    merge_sha: str | None
    reason: str             # human-readable explanation


async def attempt_auto_merge(
    *,
    state: dict[str, Any],
    pr_url: str,
    pr_number: int,
    repository_full_name: str,
    incident_id: str,
    retry_count: int = 0,
) -> AutoMergeResult:
    """
    Attempt to squash-merge a PR if ENABLE_AUTO_MERGE=true and conditions are met.

    Returns an AutoMergeResult in all cases (never raises).
    """
    from backend.recovery_ext.flags import get_flags
    from backend.orchestration.telemetry import emit_node_event

    flags = get_flags()

    if not flags.enable_auto_merge:
        return AutoMergeResult(
            merged=False,
            method="skipped",
            pr_url=pr_url,
            pr_number=pr_number,
            merge_sha=None,
            reason="ENABLE_AUTO_MERGE is false — PR left open for manual merge.",
        )

    # Safety gate: only ALLOW-decision PRs may be auto-merged.
    action_decision: str = state.get("action_decision", "ALLOW")
    human_approved: bool = bool(state.get("human_approved", False))

    if action_decision == "BLOCK":
        return AutoMergeResult(
            merged=False,
            method="skipped",
            pr_url=pr_url,
            pr_number=pr_number,
            merge_sha=None,
            reason="BLOCK decision: PR will not be merged.",
        )

    if action_decision == "APPROVE" and not human_approved:
        return AutoMergeResult(
            merged=False,
            method="skipped",
            pr_url=pr_url,
            pr_number=pr_number,
            merge_sha=None,
            reason="APPROVE decision requires operator approval before auto-merge.",
        )

    # Emit intent event
    await emit_node_event(
        incident_id=incident_id,
        event_type="auto_merge_started",
        node_name="auto_merge",
        message=f"[AUTO_MERGE] Attempting squash merge of PR #{pr_number} ({pr_url}).",
        metadata={"pr_number": pr_number, "pr_url": pr_url, "decision": action_decision},
        retry_count=retry_count,
    )

    result = await _do_merge(
        repository_full_name=repository_full_name,
        pr_number=pr_number,
        pr_url=pr_url,
        incident_id=incident_id,
    )

    # Emit result event
    await emit_node_event(
        incident_id=incident_id,
        event_type="auto_merge_completed" if result.merged else "auto_merge_refused",
        node_name="auto_merge",
        message=(
            f"[AUTO_MERGE] PR #{pr_number} {'squash-merged ✓' if result.merged else 'not merged'}: {result.reason}"
        ),
        metadata={
            "merged": result.merged,
            "method": result.method,
            "merge_sha": result.merge_sha,
            "reason": result.reason,
            "pr_number": pr_number,
        },
        retry_count=retry_count,
    )
    
    if result.merged and result.merge_sha:
        # Phase 7: Post merge verification poller fallback
        try:
            from backend.recovery_ext.post_merge import start_bounded_poller
            await start_bounded_poller(
                incident_id=incident_id,
                pr_number=pr_number,
                repository_full_name=repository_full_name,
            )
        except Exception as e:
            logger.warning(f"[AUTO_MERGE] Failed to start bounded poller: {e}")

    return result


async def _do_merge(
    *,
    repository_full_name: str,
    pr_number: int,
    pr_url: str,
    incident_id: str,
) -> AutoMergeResult:
    """
    Perform the actual GitHub merge call (synchronous PyGithub in thread).
    """
    import asyncio

    def _sync_merge() -> AutoMergeResult:
        try:
            from github import Github, Auth
            from github.GithubException import GithubException
            from backend.config.github_config import GitHubSettings

            settings = GitHubSettings()  # type: ignore[call-arg]
            if not settings.token:
                return AutoMergeResult(
                    merged=False,
                    method="error",
                    pr_url=pr_url,
                    pr_number=pr_number,
                    merge_sha=None,
                    reason="GITHUB_TOKEN not configured; cannot auto-merge.",
                )

            try:
                auth = Auth.Token(settings.token)
                gh = Github(auth=auth, timeout=20)
            except Exception:
                gh = Github(login_or_token=settings.token, timeout=20)

            repo = gh.get_repo(repository_full_name)
            pr = repo.get_pull(pr_number)

            if pr.is_merged():
                return AutoMergeResult(
                    merged=True,
                    method="squash",
                    pr_url=pr_url,
                    pr_number=pr_number,
                    merge_sha=pr.merge_commit_sha,
                    reason="PR was already merged.",
                )

            if not pr.mergeable:
                return AutoMergeResult(
                    merged=False,
                    method="refused",
                    pr_url=pr_url,
                    pr_number=pr_number,
                    merge_sha=None,
                    reason=f"PR is not mergeable (state: {pr.mergeable_state}). Left open.",
                )

            commit_msg = (
                f"fix({incident_id}): Autonomous recovery patch — squash merge\n\n"
                f"Merged by Autonomous Recovery Engine.\n"
                f"Incident: {incident_id}\n"
                f"PR: {pr_url}\n"
            )

            merge_result = pr.merge(
                commit_message=commit_msg,
                merge_method="squash",
            )

            if merge_result.merged:
                return AutoMergeResult(
                    merged=True,
                    method="squash",
                    pr_url=pr_url,
                    pr_number=pr_number,
                    merge_sha=merge_result.sha,
                    reason=f"Squash-merged: {merge_result.message}",
                )
            else:
                return AutoMergeResult(
                    merged=False,
                    method="refused",
                    pr_url=pr_url,
                    pr_number=pr_number,
                    merge_sha=None,
                    reason=f"GitHub refused the merge: {merge_result.message}. PR left open.",
                )

        except Exception as exc:
            # 405 = branch protection, 422 = merge conflict / not allowed
            reason = str(exc)
            if "405" in reason or "Method Not Allowed" in reason:
                reason = "Branch protection rules prevented the merge. PR left open."
            elif "422" in reason:
                reason = f"GitHub rejected the merge (422 — merge conflict or protection): {reason}. PR left open."
            logger.warning("[AUTO_MERGE] merge failed (non-fatal): %s", reason)
            return AutoMergeResult(
                merged=False,
                method="error",
                pr_url=pr_url,
                pr_number=pr_number,
                merge_sha=None,
                reason=reason,
            )

    return await asyncio.get_event_loop().run_in_executor(None, _sync_merge)
