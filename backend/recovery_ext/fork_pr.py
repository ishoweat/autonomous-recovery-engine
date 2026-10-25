"""
recovery_ext/fork_pr.py
───────────────────────
Phase 10: Fork-and-PR mode extensions.

Provides:
  - Access level classification (OWNER_WRITE, FORK_REQUIRED, PRIVATE_NO_ACCESS, ARCHIVED, FORKING_DISABLED, NOT_FOUND)
  - Opt-out detection via .github/ai-recovery.yml
  - PR template fetching (.github/PULL_REQUEST_TEMPLATE.md)
  - Stale fork synchronization
  - Consent tracking (fork_pr_consents DB table)
  - Public demo mode allowlist verification
  - Fork PR upstream status polling
"""
from __future__ import annotations

import os
import logging
from enum import Enum
from typing import Any, Optional
import aiosqlite

logger = logging.getLogger(__name__)


class AccessLevel(str, Enum):
    OWNER_WRITE = "OWNER_WRITE"
    FORK_REQUIRED = "FORK_REQUIRED"
    PRIVATE_NO_ACCESS = "PRIVATE_NO_ACCESS"
    ARCHIVED = "ARCHIVED"
    FORKING_DISABLED = "FORKING_DISABLED"
    NOT_FOUND = "NOT_FOUND"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Access Classification
# ─────────────────────────────────────────────────────────────────────────────

def classify_repo_access(
    repository_full_name: str,
    user_token: str,
    allow_private: bool = False,
) -> tuple[AccessLevel, dict[str, Any]]:
    """
    Classify repository access using only the logged-in user's token.
    Returns (AccessLevel, repo_metadata).
    """
    from github import Github, Auth
    from github.GithubException import UnknownObjectException, GithubException

    if not user_token:
        return AccessLevel.NOT_FOUND, {"reason": "No user token provided"}

    try:
        try:
            auth = Auth.Token(user_token)
            gh = Github(auth=auth, timeout=10)
        except Exception:
            gh = Github(login_or_token=user_token, timeout=10)

        repo = gh.get_repo(repository_full_name)
    except UnknownObjectException:
        return AccessLevel.NOT_FOUND, {"reason": "Repository not found"}
    except GithubException as exc:
        if exc.status in (401, 403, 404):
            return AccessLevel.PRIVATE_NO_ACCESS, {"reason": str(exc)}
        return AccessLevel.NOT_FOUND, {"reason": str(exc)}

    meta = {
        "full_name": repo.full_name,
        "private": repo.private,
        "archived": getattr(repo, "archived", False),
        "allow_forking": getattr(repo, "allow_forking", True),
        "permissions": getattr(repo, "permissions", None),
        "default_branch": repo.default_branch,
    }

    if meta["archived"]:
        return AccessLevel.ARCHIVED, meta

    if meta["private"] and not allow_private:
        return AccessLevel.PRIVATE_NO_ACCESS, meta

    if not meta["allow_forking"]:
        return AccessLevel.FORKING_DISABLED, meta

    has_push = bool(repo.permissions and repo.permissions.push)
    if has_push:
        return AccessLevel.OWNER_WRITE, meta

    return AccessLevel.FORK_REQUIRED, meta


# ─────────────────────────────────────────────────────────────────────────────
# 2. .github/ai-recovery.yml Opt-Out Check
# ─────────────────────────────────────────────────────────────────────────────

def check_ai_recovery_opt_out(repository_full_name: str, user_token: str) -> bool:
    """
    Check if the repository explicitly opts out via .github/ai-recovery.yml.
    Returns True if opted out, False otherwise.
    """
    from github import Github, Auth
    from github.GithubException import UnknownObjectException

    try:
        try:
            auth = Auth.Token(user_token)
            gh = Github(auth=auth, timeout=10)
        except Exception:
            gh = Github(login_or_token=user_token, timeout=10)

        repo = gh.get_repo(repository_full_name)
        file_content = repo.get_contents(".github/ai-recovery.yml")
        content_str = file_content.decoded_content.decode("utf-8", errors="ignore").lower()
        if "opt_out: true" in content_str or "enabled: false" in content_str:
            logger.info("Repository %s has opted out via .github/ai-recovery.yml", repository_full_name)
            return True
    except (UnknownObjectException, Exception):
        pass
    return False


# ─────────────────────────────────────────────────────────────────────────────
# 3. PR Template Fetcher
# ─────────────────────────────────────────────────────────────────────────────

def get_pr_template_content(repository_full_name: str, user_token: str) -> Optional[str]:
    """
    Fetch .github/PULL_REQUEST_TEMPLATE.md if present.
    """
    from github import Github, Auth
    from github.GithubException import UnknownObjectException

    for path in [".github/PULL_REQUEST_TEMPLATE.md", ".github/pull_request_template.md", "PULL_REQUEST_TEMPLATE.md"]:
        try:
            try:
                auth = Auth.Token(user_token)
                gh = Github(auth=auth, timeout=10)
            except Exception:
                gh = Github(login_or_token=user_token, timeout=10)

            repo = gh.get_repo(repository_full_name)
            file_content = repo.get_contents(path)
            return file_content.decoded_content.decode("utf-8", errors="ignore")
        except (UnknownObjectException, Exception):
            continue
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Stale Fork Sync
# ─────────────────────────────────────────────────────────────────────────────

def sync_stale_fork(fork_full_name: str, upstream_full_name: str, base_branch: str, user_token: str) -> bool:
    """
    Sync stale fork default branch from upstream (without force-push).
    """
    from github import Github, Auth
    try:
        try:
            auth = Auth.Token(user_token)
            gh = Github(auth=auth, timeout=15)
        except Exception:
            gh = Github(login_or_token=user_token, timeout=15)

        fork_repo = gh.get_repo(fork_full_name)
        upstream_repo = gh.get_repo(upstream_full_name)
        upstream_sha = upstream_repo.get_branch(base_branch).commit.sha

        # Try merging upstream branch into fork branch
        fork_repo.merge(base_branch, upstream_sha, f"sync: catch up with {upstream_full_name}:{base_branch}")
        logger.info("Synced fork %s with upstream %s branch %s", fork_full_name, upstream_full_name, base_branch)
        return True
    except Exception as exc:
        logger.warning("Fork sync non-fatal warning: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 5. Consent Database (fork_pr_consents)
# ─────────────────────────────────────────────────────────────────────────────

from contextlib import asynccontextmanager

DB_PATH = os.getenv("DATABASE_PATH", "./recovery.db")

@asynccontextmanager
async def _connect_sqlite(db_path: str = DB_PATH):
    async with aiosqlite.connect(db_path, timeout=30.0) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA busy_timeout=30000;")
        yield db

async def init_fork_consent_db(db_path: str = DB_PATH) -> None:
    """Initialize fork_pr_consents table if not exists."""
    async with _connect_sqlite(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fork_pr_consents (
                user_id TEXT NOT NULL,
                repo_full_name TEXT NOT NULL,
                consented_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, repo_full_name)
            )
        """)
        await db.commit()


async def record_fork_consent(user_id: str, repo_full_name: str, db_path: str = DB_PATH) -> None:
    """Record explicit user consent for fork and PR on external repo."""
    await init_fork_consent_db(db_path)
    async with _connect_sqlite(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO fork_pr_consents (user_id, repo_full_name) VALUES (?, ?)",
            (user_id, repo_full_name),
        )
        await db.commit()


async def check_fork_consent(user_id: str, repo_full_name: str, db_path: str = DB_PATH) -> bool:
    """Check if explicit user consent exists."""
    await init_fork_consent_db(db_path)
    async with _connect_sqlite(db_path) as db:
        async with db.execute(
            "SELECT 1 FROM fork_pr_consents WHERE user_id = ? AND repo_full_name = ?",
            (user_id, repo_full_name),
        ) as cursor:
            row = await cursor.fetchone()
            return bool(row)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Public Demo Mode Allowlist
# ─────────────────────────────────────────────────────────────────────────────

def is_repo_allowed_in_demo_mode(repository_full_name: str) -> bool:
    """
    Check if repository is allowed in PUBLIC_DEMO_MODE.
    Reads PUBLIC_DEMO_ALLOWLIST (comma-separated).
    """
    raw_allowlist = os.getenv("PUBLIC_DEMO_ALLOWLIST", "octocat/Hello-World,Sahil707-pop/autonomous-recovery-engine")
    allowed_repos = {r.strip().lower() for r in raw_allowlist.split(",") if r.strip()}
    return repository_full_name.lower() in allowed_repos


# ─────────────────────────────────────────────────────────────────────────────
# 7. Fork PR Upstream Status Poller
# ─────────────────────────────────────────────────────────────────────────────

async def poll_fork_pr_status(repository_full_name: str, pr_number: int, user_token: str) -> dict[str, Any]:
    """
    Poll upstream PR status to distinguish merged vs closed-without-merge.
    """
    import asyncio

    def _sync_check() -> dict[str, Any]:
        from github import Github, Auth
        try:
            auth = Auth.Token(user_token)
            gh = Github(auth=auth, timeout=10)
        except Exception:
            gh = Github(login_or_token=user_token, timeout=10)

        repo = gh.get_repo(repository_full_name)
        pr = repo.get_pull(pr_number)
        return {
            "state": pr.state,          # "open" | "closed"
            "merged": pr.merged,        # True | False
            "closed_without_merge": pr.state == "closed" and not pr.merged,
            "merge_commit_sha": pr.merge_commit_sha,
        }

    return await asyncio.get_event_loop().run_in_executor(None, _sync_check)
