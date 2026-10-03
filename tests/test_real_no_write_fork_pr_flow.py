import asyncio
import os
import uuid
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from github.GithubException import GithubException

from backend.integrations.github_tools import (
    GitHubTools,
    PullRequestResult,
    GitHubForkTimeoutError,
    GitHubRepositoryError,
)
from backend.config.github_config import GitHubSettings


@pytest.mark.asyncio
async def test_no_write_fork_pr_flow_events_and_binding():
    """
    Verify NO WRITE path for an authenticated OAuth user:
    NO WRITE → create fork under authenticated user → bounded readiness retry
    → create recovery branch → commit verified patch → create cross-repo PR
    from username:branch to upstream default branch.

    Emits all 6 required SSE events:
    access_determined -> fork_created -> fork_ready -> branch_created -> commit_created -> pr_created
    """
    settings = GitHubSettings(token="gho_test_oauth_user_token_12345")
    tools = GitHubTools(settings)

    events = []

    async def event_collector(event_type: str, message: str, metadata: dict):
        events.append((event_type, message, metadata))

    # Setup PyGithub mocks
    mock_upstream_repo = MagicMock()
    mock_upstream_repo.full_name = "upstream-org/public-repo"
    # User has READ but NO WRITE access (permissions.push = False)
    mock_upstream_repo.permissions = MagicMock()
    mock_upstream_repo.permissions.push = False
    mock_upstream_repo.get_pulls.return_value = []

    mock_fork_repo = MagicMock()
    mock_fork_repo.full_name = "oauth-user/public-repo"
    mock_fork_repo.get_branch.return_value.commit.sha = "base_head_sha_98765"
    mock_fork_repo.create_git_ref.return_value = None
    mock_fork_repo.get_contents.return_value.sha = "existing_file_sha"
    mock_fork_repo.update_file.return_value = {
        "commit": MagicMock(sha="verified_commit_sha_abc123")
    }

    mock_user = MagicMock()
    mock_user.login = "oauth-user"
    mock_user.create_fork.return_value = mock_fork_repo

    mock_pull = MagicMock()
    mock_pull.html_url = "https://github.com/upstream-org/public-repo/pull/42"
    mock_pull.number = 42
    mock_upstream_repo.create_pull.return_value = mock_pull

    def get_repo_side_effect(name):
        if name == "upstream-org/public-repo":
            return mock_upstream_repo
        elif name == "oauth-user/public-repo":
            return mock_fork_repo
        raise GitHubRepositoryError(f"Unknown repo {name}")

    with patch.object(tools.client, "get_repo", side_effect=get_repo_side_effect), \
         patch.object(tools.client, "get_user", return_value=mock_user):

        incident_id = f"inc_{uuid.uuid4().hex[:8]}"
        commit_sha = "verified_commit_sha_abc123"
        branch_name = f"recovery/fix-{incident_id[:8]}-abc12345"

        result = await tools.create_recovery_pr_full(
            repository_full_name="upstream-org/public-repo",
            branch_name=branch_name,
            base_branch="main",
            file_path="src/calculator.py",
            content="def add(a, b):\n    return a + b\n",
            commit_message="fix(src/calculator.py): verified patch fix",
            pr_title="fix: resolve zero division bug",
            pr_body="Detailed PR description",
            on_event=event_collector,
        )

        # 1. Verify result dataclass binding
        assert isinstance(result, PullRequestResult)
        assert result.access_level == "FORK"
        assert result.fork_repo == "oauth-user/public-repo"
        assert result.branch_name == branch_name
        assert result.commit_sha == "verified_commit_sha_abc123"
        assert result.pr_url == "https://github.com/upstream-org/public-repo/pull/42"
        assert result.pr_number == 42
        assert result.reused is False

        # 2. Verify all 6 SSE events in order
        event_types = [e[0] for e in events]
        expected_types = [
            "access_determined",
            "fork_created",
            "fork_ready",
            "branch_created",
            "commit_created",
            "pr_created",
        ]
        assert event_types == expected_types, f"Expected {expected_types}, got {event_types}"

        # 3. Verify cross-repo PR call details
        mock_upstream_repo.create_pull.assert_called_once_with(
            title="fix: resolve zero division bug",
            body="Detailed PR description",
            head="oauth-user:" + branch_name,
            base="main",
        )

        # 4. Verify branch created on FORK repo
        mock_fork_repo.create_git_ref.assert_called_once_with(
            ref=f"refs/heads/{branch_name}",
            sha="base_head_sha_98765",
        )

        print("✅ NO WRITE FORK -> PR flow verified with all 6 events and cross-repo PR formatting.")


@pytest.mark.asyncio
async def test_reuse_existing_fork_pr():
    """
    Verify that an existing matching cross-repo PR on the fork path is reused,
    not treated as a failure or duplicate error.
    """
    settings = GitHubSettings(token="gho_test_oauth_user_token_12345")
    tools = GitHubTools(settings)

    events = []

    async def event_collector(event_type: str, message: str, metadata: dict):
        events.append((event_type, message, metadata))

    mock_upstream_repo = MagicMock()
    mock_upstream_repo.permissions = MagicMock()
    mock_upstream_repo.permissions.push = False  # NO WRITE access

    # Existing PR for head oauth-user:recovery/fix-branch
    existing_pr = MagicMock()
    existing_pr.html_url = "https://github.com/upstream-org/public-repo/pull/99"
    existing_pr.number = 99
    # Initial get_pulls before prepare_repo returns empty, second check returns existing_pr
    mock_upstream_repo.get_pulls.side_effect = [[], [existing_pr]]

    mock_fork_repo = MagicMock()
    mock_fork_repo.full_name = "oauth-user/public-repo"
    mock_fork_repo.get_branch.return_value.commit.sha = "base_sha"

    mock_user = MagicMock()
    mock_user.login = "oauth-user"
    mock_user.create_fork.return_value = mock_fork_repo

    def get_repo_side_effect(name):
        if name == "upstream-org/public-repo":
            return mock_upstream_repo
        elif name == "oauth-user/public-repo":
            return mock_fork_repo
        raise GitHubRepositoryError(f"Unknown repo {name}")

    with patch.object(tools.client, "get_repo", side_effect=get_repo_side_effect), \
         patch.object(tools.client, "get_user", return_value=mock_user):

        branch_name = "recovery/fix-inc1234-sha5678"
        result = await tools.create_recovery_pr_full(
            repository_full_name="upstream-org/public-repo",
            branch_name=branch_name,
            base_branch="main",
            file_path="src/calculator.py",
            content="fixed",
            commit_message="fix",
            pr_title="title",
            pr_body="body",
            on_event=event_collector,
        )

        assert result.reused is True
        assert result.pr_url == "https://github.com/upstream-org/public-repo/pull/99"
        assert result.pr_number == 99
        assert result.access_level == "FORK"
        assert result.fork_repo == "oauth-user/public-repo"

        event_types = [e[0] for e in events]
        assert "pr_reused" in event_types
        print("✅ Existing matching fork PR reuse verified.")


@pytest.mark.asyncio
async def test_github_api_failure_fails_loudly():
    """
    Verify GitHub API errors fail loudly without simulating success.
    """
    settings = GitHubSettings(token="gho_test_oauth_user_token_12345")
    tools = GitHubTools(settings)

    with patch.object(tools.client, "get_repo", side_effect=GithubException(403, "API rate limit exceeded", None)):
        with pytest.raises(GitHubRepositoryError) as exc_info:
            tools.check_write_access("upstream-org/public-repo")
        assert "Unable to access GitHub repository" in str(exc_info.value)

    print("✅ GitHub API error fails loudly without mock fallback.")


@pytest.mark.asyncio
async def test_live_fork_flow_against_public_repo():
    """
    Real live test against a public repository where the OAuth user has no write access.
    Skipped unless GITHUB_TOKEN is present in environment.
    """
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_OAUTH_TOKEN")
    if not token or token.startswith("your_"):
        pytest.skip("Skipping live GitHub test: GITHUB_TOKEN environment variable not set.")

    settings = GitHubSettings(token=token)
    tools = GitHubTools(settings)

    public_repo = "octocat/Hello-World"

    print(f"\n[LIVE TEST] 1. Checking write access on public repository '{public_repo}'...")
    has_write = tools.check_write_access(public_repo)
    user_login = tools.get_authenticated_user_login()
    print(f"[LIVE TEST] Authenticated user: {user_login}, Write access on {public_repo}: {has_write}")

    if has_write:
        print(f"[LIVE TEST] User '{user_login}' has write access to {public_repo}. Skipping fork test.")
        return

    print(f"[LIVE TEST] 2. User '{user_login}' has READ ONLY access. Preparing fork recovery repo...")
    events = []

    async def log_event(evt_type, msg, meta):
        print(f"  [SSE EVENT] {evt_type}: {msg}")
        events.append(evt_type)

    target_repo, pr_head_prefix, access_level, fork_full_name = await tools.prepare_recovery_repo(
        public_repo, "master", on_event=log_event
    )

    print(f"[LIVE TEST] Result: target={target_repo}, prefix={pr_head_prefix}, access={access_level}, fork={fork_full_name}")
    assert access_level == "FORK"
    assert pr_head_prefix == f"{user_login}:"
    assert fork_full_name == f"{user_login}/Hello-World"
    assert "access_determined" in events
    assert "fork_created" in events or "fork_ready" in events

    print("✅ LIVE TEST PASSED for public repo NO WRITE fork readiness path!")
