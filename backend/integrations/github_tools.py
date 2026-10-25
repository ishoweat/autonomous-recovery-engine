from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Mapping

from github import Github
from github.GithubException import GithubException, UnknownObjectException
from github.Repository import Repository

from backend.config.github_config import GitHubSettings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — fork-readiness polling
# ---------------------------------------------------------------------------
_FORK_POLL_INTERVAL_S: float = 3.0   # seconds between readiness probes
_FORK_POLL_MAX_WAIT_S: float = 60.0  # absolute ceiling; raise if exceeded


# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PullRequestResult:
    branch_name: str
    commit_sha: str
    pr_url: str
    pr_number: int
    access_level: str = "WRITE"   # "WRITE" | "FORK"
    fork_repo: str = ""           # only set when access_level == "FORK"
    reused: bool = False          # True when an existing PR was reused


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class GitHubIntegrationError(RuntimeError):
    """Base GitHub integration error."""


class GitHubRepositoryError(GitHubIntegrationError):
    """Repository access or fork failure."""


class GitHubForkTimeoutError(GitHubIntegrationError):
    """Fork did not become ready within the allowed window."""


class GitHubBranchError(GitHubIntegrationError):
    """Branch creation failure."""


class GitHubCommitError(GitHubIntegrationError):
    """Commit operation failure."""


class GitHubPullRequestError(GitHubIntegrationError):
    """Pull request creation failure."""


# ---------------------------------------------------------------------------
# GitHubTools
# ---------------------------------------------------------------------------

class GitHubTools:
    """
    GitHub REST API integration using PyGithub.

    Three recovery paths:
      WRITE  — branch + commit + PR on the original repository.
      FORK   — fork repo → poll until ready → branch + commit + PR upstream.
      REUSE  — detect an existing open PR for the same branch; return it.

    The service never exposes the GitHub token to the sandbox or logs.
    """

    def __init__(self, settings: GitHubSettings) -> None:
        self.settings = settings
        try:
            from github import Auth
            auth = Auth.Token(settings.token)
            self.client = Github(auth=auth, timeout=10, retry=2, per_page=100)
        except Exception:
            self.client = Github(login_or_token=settings.token, timeout=10, retry=2, per_page=100)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_repository(self, repository_full_name: str) -> Repository:
        try:
            return self.client.get_repo(repository_full_name)
        except UnknownObjectException as exc:
            raise GitHubRepositoryError(
                f"GitHub repository not found: {repository_full_name}"
            ) from exc
        except GithubException as exc:
            raise GitHubRepositoryError(
                f"Unable to access GitHub repository: {exc}"
            ) from exc

    def _get_base_branch_sha(self, repository: Repository, base_branch: str) -> str:
        try:
            branch = repository.get_branch(base_branch)
        except GithubException as exc:
            raise GitHubBranchError(
                f"Unable to resolve base branch '{base_branch}': {exc}"
            ) from exc
        return branch.commit.sha

    # ------------------------------------------------------------------
    # Authentication helpers
    # ------------------------------------------------------------------

    def get_authenticated_user_login(self) -> str:
        """Return the login of the currently authenticated GitHub user."""
        try:
            return self.client.get_user().login
        except GithubException as exc:
            raise GitHubRepositoryError(
                f"Unable to retrieve authenticated user: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Access-level detection
    # ------------------------------------------------------------------

    def check_write_access(self, repository_full_name: str) -> bool:
        """
        Return True when the authenticated user has push access.

        PyGithub only populates ``repo.permissions`` when the token owner
        is a collaborator.  For public repos with a non-collaborator token
        the attribute is ``None`` — treated as NO write access.
        """
        repo = self._get_repository(repository_full_name)
        return bool(repo.permissions and repo.permissions.push)

    # ------------------------------------------------------------------
    # Fork + readiness polling
    # ------------------------------------------------------------------

    def _fork_repository(self, repository_full_name: str) -> tuple[str, str]:
        """
        Fork *repository_full_name* into the authenticated user's account.

        Returns ``(fork_full_name, user_login)``.
        """
        repo = self._get_repository(repository_full_name)
        user = self.client.get_user()
        try:
            fork = user.create_fork(repo)
        except GithubException as exc:
            raise GitHubRepositoryError(
                f"Unable to fork {repository_full_name}: {exc}"
            ) from exc
        return fork.full_name, user.login

    async def wait_for_fork_ready(
        self,
        fork_full_name: str,
        base_branch: str,
        *,
        poll_interval: float = _FORK_POLL_INTERVAL_S,
        max_wait: float = _FORK_POLL_MAX_WAIT_S,
        on_event: Callable[[str, str, dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        """
        Poll the fork until its default branch is accessible or *max_wait*
        seconds have elapsed.

        GitHub's fork API returns immediately but Git objects (branches,
        commits) may take several seconds to propagate.  Bounded retry
        polling avoids an arbitrary ``sleep`` while handling the race.

        *on_event*, if provided, is called as
        ``await on_event(event_type, message, metadata)`` at key milestones:
        - ``fork_ready``  once the fork's branch is accessible.

        Raises :class:`GitHubForkTimeoutError` if the fork is not ready.
        """
        deadline = time.monotonic() + max_wait
        attempt = 0
        while time.monotonic() < deadline:
            attempt += 1
            try:
                fork_repo = self._get_repository(fork_full_name)
                fork_repo.get_branch(base_branch)
                logger.info(
                    "Fork %s ready after %d probe(s).", fork_full_name, attempt
                )
                if on_event:
                    await on_event(
                        "fork_ready",
                        f"Fork {fork_full_name} is ready (branch '{base_branch}' accessible after {attempt} probe(s)).",
                        {"fork_repo": fork_full_name, "base_branch": base_branch, "probes": attempt},
                    )
                return
            except (GithubException, GitHubRepositoryError):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                sleep_for = min(poll_interval, remaining)
                logger.debug(
                    "Fork %s not yet ready (probe %d); retrying in %.1fs ...",
                    fork_full_name, attempt, sleep_for,
                )
                await asyncio.sleep(sleep_for)

        raise GitHubForkTimeoutError(
            f"Fork {fork_full_name} did not become ready within "
            f"{max_wait:.0f}s ({attempt} probe(s))."
        )

    # ------------------------------------------------------------------
    # Prepare — returns (target_repo, pr_head_prefix, access_level, fork_repo)
    # ------------------------------------------------------------------

    async def prepare_recovery_repo(
        self,
        repository_full_name: str,
        base_branch: str = "main",
        *,
        on_event: Callable[[str, str, dict[str, Any]], Awaitable[None]] | None = None,
    ) -> tuple[str, str, str, str]:
        """
        Determine the target repository for the recovery branch.

        Returns::

            (target_repo_full_name, pr_head_prefix, access_level, fork_full_name)

        WRITE path: branch on original repo, pr_head_prefix = "".
        FORK  path: fork created + polled, pr_head_prefix = "owner:".

        *on_event* receives ``access_determined``, ``fork_created``, ``fork_ready``.
        """
        has_write = self.check_write_access(repository_full_name)
        if has_write:
            logger.info("WRITE access confirmed for %s.", repository_full_name)
            if on_event:
                await on_event(
                    "access_determined",
                    f"WRITE access confirmed for {repository_full_name}. Branch will be created directly.",
                    {"access_level": "WRITE", "original_repo": repository_full_name},
                )
            return repository_full_name, "", "WRITE", ""

        from backend.recovery_ext.flags import get_flags
        if not get_flags().enable_fork_and_pr:
            logger.info("No WRITE access to %s and ENABLE_FORK_AND_PR is false — defaulting to WRITE path.", repository_full_name)
            if on_event:
                await on_event(
                    "access_determined",
                    f"WRITE access assumed for {repository_full_name} (ENABLE_FORK_AND_PR is false).",
                    {"access_level": "WRITE", "original_repo": repository_full_name},
                )
            return repository_full_name, "", "WRITE", ""

        logger.info("No WRITE access to %s — forking ...", repository_full_name)
        if on_event:
            await on_event(
                "access_determined",
                f"No WRITE access to {repository_full_name}. Forking into authenticated user's account ...",
                {"access_level": "FORK", "original_repo": repository_full_name},
            )

        fork_full_name, user_login = self._fork_repository(repository_full_name)
        logger.info("Fork created: %s (owner: %s)", fork_full_name, user_login)
        if on_event:
            await on_event(
                "fork_created",
                f"Fork created: {fork_full_name} (owner: {user_login}). Polling for readiness ...",
                {"fork_repo": fork_full_name, "user_login": user_login, "original_repo": repository_full_name},
            )

        await self.wait_for_fork_ready(fork_full_name, base_branch, on_event=on_event)

        return fork_full_name, f"{user_login}:", "FORK", fork_full_name

    # ------------------------------------------------------------------
    # Existing-PR detection
    # ------------------------------------------------------------------

    def get_existing_pr_info(
        self,
        repository_full_name: str,
        branch_name: str,
        pr_head_prefix: str = "",
    ) -> tuple[str, int, str] | tuple[None, None, None]:
        """
        Search for an open PR whose head matches *branch_name*.

        Returns ``(pr_url, pr_number, head_sha)`` when found, otherwise ``(None, None, None)``.
        """
        try:
            repo = self._get_repository(repository_full_name)
            head_filter = (
                f"{pr_head_prefix}{branch_name}"
                if pr_head_prefix
                else branch_name
            )
            pulls = repo.get_pulls(state="open", head=head_filter)
            for pr in pulls:
                head_sha = getattr(getattr(pr, "head", None), "sha", "") or ""
                logger.info(
                    "Found existing PR #%d for branch %s: %s (head_sha: %s)",
                    pr.number, branch_name, pr.html_url, head_sha,
                )
                return pr.html_url, pr.number, head_sha
        except GithubException:
            pass
        return None, None, None

    def get_existing_pr(
        self,
        repository_full_name: str,
        branch_name: str,
        pr_head_prefix: str = "",
    ) -> tuple[str, int] | tuple[None, None]:
        """
        Search for an open PR whose head matches *branch_name*.

        GitHub requires ``owner:branch`` for cross-repo (fork) PRs.

        Returns ``(pr_url, pr_number)`` when found, otherwise ``(None, None)``.
        """
        url, number, _ = self.get_existing_pr_info(repository_full_name, branch_name, pr_head_prefix)
        return url, number

    # ------------------------------------------------------------------
    # Branch / commit / PR primitives
    # ------------------------------------------------------------------

    def create_branch(
        self,
        repository_full_name: str,
        branch_name: str,
        base_branch: str,
    ) -> str:
        repository = self._get_repository(repository_full_name)
        base_sha = self._get_base_branch_sha(repository, base_branch)
        try:
            repository.create_git_ref(
                ref=f"refs/heads/{branch_name}",
                sha=base_sha,
            )
        except GithubException as exc:
            raise GitHubBranchError(
                f"Unable to create branch '{branch_name}': {exc}"
            ) from exc
        return branch_name

    def commit_file(
        self,
        repository_full_name: str,
        branch_name: str,
        file_path: str,
        content: str,
        commit_message: str,
    ) -> str:
        repository = self._get_repository(repository_full_name)
        normalized_path = file_path.strip("/")

        if not normalized_path:
            raise GitHubCommitError("Cannot commit an empty file path.")

        if normalized_path.endswith(".py") and content:
            from backend.services.code_cleaner import validate_and_clean_code
            content, _, _ = validate_and_clean_code(content)

        try:
            existing_file = repository.get_contents(
                normalized_path, ref=branch_name
            )
            if isinstance(existing_file, list):
                raise GitHubCommitError(
                    f"'{normalized_path}' resolves to a directory."
                )
            response = repository.update_file(
                path=normalized_path,
                message=commit_message,
                content=content,
                sha=existing_file.sha,
                branch=branch_name,
            )
            return response["commit"].sha

        except UnknownObjectException:
            try:
                response = repository.create_file(
                    path=normalized_path,
                    message=commit_message,
                    content=content,
                    branch=branch_name,
                )
                return response["commit"].sha
            except GithubException as exc:
                raise GitHubCommitError(
                    f"Unable to create '{normalized_path}': {exc}"
                ) from exc

        except GithubException as exc:
            raise GitHubCommitError(
                f"Unable to update '{normalized_path}': {exc}"
            ) from exc

    def commit_files(
        self,
        repository_full_name: str,
        branch_name: str,
        files: Mapping[str, str],
        commit_message: str,
    ) -> str:
        """Commit multiple files sequentially; returns the final commit SHA."""
        if not files:
            raise GitHubCommitError("At least one file is required.")
        commit_sha = ""
        for file_path, content in files.items():
            commit_sha = self.commit_file(
                repository_full_name=repository_full_name,
                branch_name=branch_name,
                file_path=file_path,
                content=content,
                commit_message=commit_message,
            )
        return commit_sha

    def create_pull_request(
        self,
        repository_full_name: str,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> str:
        repository = self._get_repository(repository_full_name)
        try:
            pull_request = repository.create_pull(
                title=title,
                body=body,
                head=head_branch,
                base=base_branch,
            )
            return pull_request.html_url
        except GithubException as exc:
            raise GitHubPullRequestError(
                f"Unable to create pull request: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # High-level: full three-path recovery flow
    # ------------------------------------------------------------------

    async def create_recovery_pr_full(
        self,
        *,
        repository_full_name: str,
        branch_name: str,
        base_branch: str,
        file_path: str,
        content: str,
        commit_message: str,
        pr_title: str,
        pr_body: str,
        on_event: Callable[[str, str, dict[str, Any]], Awaitable[None]] | None = None,
    ) -> PullRequestResult:
        """
        Execute the complete recovery flow in a single async call.

        Paths (in order):
        1. REUSE  — existing open PR for *branch_name* → returned immediately.
        2. WRITE  — push access → branch + commit + PR on original repo.
        3. FORK   — no push access → fork + readiness poll → branch + commit
                    on fork → cross-repo PR to original repo.

        *on_event*, if provided, is called as::

            await on_event(event_type, message, metadata)

        Events emitted in order:
        - ``access_determined``  (WRITE or FORK)
        - ``fork_created``       (FORK path only)
        - ``fork_ready``         (FORK path only)
        - ``branch_created``
        - ``commit_created``
        - ``pr_reused`` | ``pr_created``
        """
        # ── REUSE check (WRITE head, no prefix yet) ─────────────────────
        existing_url, existing_number, existing_sha = self.get_existing_pr_info(
            repository_full_name, branch_name
        )
        if existing_url and existing_number:
            logger.info(
                "Reusing existing PR #%d for branch %s.",
                existing_number, branch_name,
            )
            if on_event:
                await on_event(
                    "pr_reused",
                    f"Existing open PR #{existing_number} found for branch '{branch_name}' — reusing it.",
                    {
                        "pr_url": existing_url,
                        "pr_number": existing_number,
                        "branch": branch_name,
                        "commit_sha": existing_sha,
                        "reused": True,
                        "access_level": "WRITE",
                        "original_repo": repository_full_name,
                    },
                )
            return PullRequestResult(
                branch_name=branch_name,
                commit_sha=existing_sha,
                pr_url=existing_url,
                pr_number=existing_number,
                access_level="WRITE",
                reused=True,
            )

        # ── WRITE / FORK determination + fork readiness ─────────────────
        target_repo, pr_head_prefix, access_level, fork_full_name = (
            await self.prepare_recovery_repo(
                repository_full_name, base_branch, on_event=on_event
            )
        )

        # ── REUSE check (FORK head: "owner:branch") ─────────────────────
        if access_level == "FORK" and pr_head_prefix:
            existing_url, existing_number, existing_sha = self.get_existing_pr_info(
                repository_full_name, branch_name, pr_head_prefix
            )
            if existing_url and existing_number:
                logger.info(
                    "Reusing existing fork PR #%d for branch %s.",
                    existing_number, branch_name,
                )
                if on_event:
                    await on_event(
                        "pr_reused",
                        f"Existing open fork PR #{existing_number} found for branch '{branch_name}' — reusing it.",
                        {
                            "pr_url": existing_url,
                            "pr_number": existing_number,
                            "branch": branch_name,
                            "commit_sha": existing_sha,
                            "fork_repo": fork_full_name,
                            "original_repo": repository_full_name,
                            "access_level": access_level,
                            "reused": True,
                        },
                    )
                return PullRequestResult(
                    branch_name=branch_name,
                    commit_sha=existing_sha,
                    pr_url=existing_url,
                    pr_number=existing_number,
                    access_level=access_level,
                    fork_repo=fork_full_name,
                    reused=True,
                )

        # ── Create branch ────────────────────────────────────────────────
        self.create_branch(
            repository_full_name=target_repo,
            branch_name=branch_name,
            base_branch=base_branch,
        )
        if on_event:
            await on_event(
                "branch_created",
                f"Recovery branch '{branch_name}' created on {target_repo} ({access_level} path).",
                {"branch": branch_name, "target_repo": target_repo,
                 "access_level": access_level, "fork_repo": fork_full_name},
            )

        # ── Commit the fix ───────────────────────────────────────────────
        committed_sha = self.commit_file(
            repository_full_name=target_repo,
            branch_name=branch_name,
            file_path=file_path,
            content=content,
            commit_message=commit_message,
        )
        if on_event:
            await on_event(
                "commit_created",
                f"Fix committed: {committed_sha[:7]} on {target_repo} branch '{branch_name}'.",
                {"commit_sha": committed_sha, "branch": branch_name,
                 "target_repo": target_repo, "access_level": access_level,
                 "commit_message": commit_message},
            )

        # ── Open PR (fork → upstream or direct) ──────────────────────────
        pr_head = f"{pr_head_prefix}{branch_name}"
        pr_url = self.create_pull_request(
            repository_full_name=repository_full_name,
            head_branch=pr_head,
            base_branch=base_branch,
            title=pr_title,
            body=pr_body,
        )
        try:
            pr_number = int(pr_url.split("/pull/")[-1].split("/")[0])
        except (ValueError, IndexError):
            pr_number = 0

        if on_event:
            await on_event(
                "pr_created",
                f"Pull Request #{pr_number} created: {pr_url} ({access_level} path, head: {pr_head}).",
                {"pr_url": pr_url, "pr_number": pr_number, "pr_head": pr_head,
                 "access_level": access_level, "fork_repo": fork_full_name,
                 "original_repo": repository_full_name, "commit_sha": committed_sha,
                 "branch": branch_name, "reused": False},
            )

        return PullRequestResult(
            branch_name=branch_name,
            commit_sha=committed_sha,
            pr_url=pr_url,
            pr_number=pr_number,
            access_level=access_level,
            fork_repo=fork_full_name,
            reused=False,
        )

    # ------------------------------------------------------------------
    # Status API
    # ------------------------------------------------------------------

    def create_commit_status(
        self,
        repository_full_name: str,
        commit_sha: str,
        state: str,
        target_url: str,
        description: str,
        context: str = "ARE/Verification",
    ) -> None:
        """
        Create a commit status. State can be 'error', 'failure', 'pending', or 'success'.
        """
        try:
            repo = self._get_repository(repository_full_name)
            repo.get_commit(commit_sha).create_status(
                state=state,
                target_url=target_url,
                description=description[:140],
                context=context,
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(f"Failed to create commit status: {exc}")

    # ------------------------------------------------------------------
    # Legacy entry point (kept for backward compatibility)
    # ------------------------------------------------------------------

    def create_recovery_pr(
        self,
        repository_full_name: str,
        base_branch: str,
        branch_name: str,
        file_path: str,
        content: str,
        commit_message: str,
        pr_title: str,
        pr_body: str,
    ) -> PullRequestResult:
        """
        Synchronous legacy entry point — WRITE path only, no fork support.
        Prefer ``create_recovery_pr_full`` for the full three-path flow.
        """
        self.create_branch(
            repository_full_name=repository_full_name,
            branch_name=branch_name,
            base_branch=base_branch,
        )
        commit_sha = self.commit_file(
            repository_full_name=repository_full_name,
            branch_name=branch_name,
            file_path=file_path,
            content=content,
            commit_message=commit_message,
        )
        repository = self._get_repository(repository_full_name)
        try:
            pull_request = repository.create_pull(
                title=pr_title,
                body=pr_body,
                head=branch_name,
                base=base_branch,
            )
            return PullRequestResult(
                branch_name=branch_name,
                commit_sha=commit_sha,
                pr_url=pull_request.html_url,
                pr_number=pull_request.number,
            )
        except GithubException as exc:
            raise GitHubPullRequestError(
                f"Unable to create pull request: {exc}"
            )

    def get_workflow_run_logs_and_traceback(
        self, repository_full_name: str, run_id: int
    ) -> dict[str, str]:
        """
        Fetches the failed job logs for a workflow run and attempts to extract
        the pytest traceback, failing file, and error message.
        """
        import requests
        import zipfile
        import io
        import re

        repo = self._get_repository(repository_full_name)
        
        try:
            run = repo.get_workflow_run(run_id)
            logs_url = run.logs_url
            
            # Fetch the logs zip
            res = requests.get(logs_url, headers={"Authorization": f"Bearer {self.settings.token}"})
            if res.status_code != 200:
                return {"stack_trace": "Could not download logs", "failure_file": "", "error_message": f"Log download failed with status {res.status_code}"}
                
            combined_logs = ""
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                for filename in z.namelist():
                    if filename.endswith(".txt"):
                        with z.open(filename) as f:
                            combined_logs += f.read().decode("utf-8", errors="replace") + "\\n"
                            
            # Extremely basic regex extraction for pytest
            # Find lines like "FAILED tests/test_something.py::test_name - AssertionError..."
            # or traceback blocks
            stack_trace = combined_logs[-5000:] # Just grab the last 5k chars for demo simplicity if no regex match
            failure_file = ""
            error_message = "Workflow failed"
            
            # Attempt to find the FAILED line
            match = re.search(r"FAILED\s+(.*?\.py)::(.*?)\s+-\s+(.*?)$", combined_logs, re.MULTILINE)
            if match:
                failure_file = match.group(1)
                error_message = match.group(3)
                # find the traceback block that follows
                tb_start = combined_logs.find(match.group(0))
                if tb_start != -1:
                    stack_trace = combined_logs[tb_start:tb_start+2000]
            else:
                # Look for typical python traceback
                tb_match = re.search(r"Traceback \(most recent call last\):.*?(?=\n\n|\Z)", combined_logs, re.DOTALL)
                if tb_match:
                    stack_trace = tb_match.group(0)
                    file_match = re.search(r'File "(.*?\.py)"', stack_trace)
                    if file_match:
                        failure_file = file_match.group(1)
                    error_message = stack_trace.strip().split("\\n")[-1]

            return {
                "stack_trace": stack_trace.strip(),
                "failure_file": failure_file,
                "error_message": error_message
            }
        except Exception as e:
            return {"stack_trace": str(e), "failure_file": "", "error_message": f"Error extracting logs: {str(e)}"}
