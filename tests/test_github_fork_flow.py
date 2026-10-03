""" 
test_github_fork_flow.py — Real verification of the FORK → PR path.

Three test levels:
  1. UNIT   — PyGithub mocked; validates every step of the FORK logic and
              the exact sequence of on_event callbacks.
  2. UNIT   — WRITE path and REUSE path similarly verified.
  3. LIVE   — Real GitHub API call to a public repo the OAuth user cannot
              push to (octocat/Hello-World).  Skipped when GITHUB_TOKEN
              is absent or when the token has write access to the repo.

Run:
    PYTHONPATH=. pytest -v tests/test_github_fork_flow.py -s
"""
from __future__ import annotations

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from github.GithubException import UnknownObjectException

from backend.integrations.github_tools import (
    GitHubTools,
    GitHubForkTimeoutError,
    GitHubRepositoryError,
    PullRequestResult,
)
from backend.config.github_config import GitHubSettings


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_settings(token: str = "ghp_test_token") -> GitHubSettings:
    return GitHubSettings(token=token)


def _make_mock_repo(
    *,
    push: bool,
    user_login: str = "testuser",
    head_sha: str = "abc1234def5678",
    fork_full_name: str = "testuser/Hello-World",
    pr_html_url: str = "https://github.com/octocat/Hello-World/pull/42",
    pr_number: int = 42,
    existing_pulls: list | None = None,
):
    """
    Build a MagicMock that stands in for a PyGithub Repository plus the
    Github client.  Returns (mock_github_class, mock_repo, mock_fork_repo).
    """
    # Original repo
    mock_orig_repo = MagicMock()
    mock_orig_repo.permissions = MagicMock()
    mock_orig_repo.permissions.push = push
    mock_orig_repo.get_branch.return_value.commit.sha = head_sha

    # Pull-request mock
    mock_pull = MagicMock()
    mock_pull.html_url = pr_html_url
    mock_pull.number = pr_number
    mock_orig_repo.create_pull.return_value = mock_pull

    # Existing PRs (for REUSE path)
    mock_orig_repo.get_pulls.return_value = iter(existing_pulls or [])

    # Fork repo
    mock_fork_repo = MagicMock()
    mock_fork_repo.full_name = fork_full_name
    mock_fork_repo.get_branch.return_value.commit.sha = head_sha
    mock_fork_repo.create_git_ref.return_value = None
    # Raise UnknownObjectException so commit_file falls through to create_file
    mock_fork_repo.get_contents.side_effect = UnknownObjectException(404, {"message": "Not Found"}, {})
    mock_fork_repo.create_file.return_value = {
        "commit": MagicMock(sha="committed999")
    }

    # User mock
    mock_user = MagicMock()
    mock_user.login = user_login
    mock_user.create_fork.return_value = mock_fork_repo

    # Github client mock
    mock_github_client = MagicMock()

    def _get_repo(name):
        if name == fork_full_name:
            return mock_fork_repo
        return mock_orig_repo

    mock_github_client.get_repo.side_effect = _get_repo
    mock_github_client.get_user.return_value = mock_user

    # Github class mock
    mock_github_class = MagicMock()
    mock_github_class.return_value = mock_github_client

    return mock_github_class, mock_orig_repo, mock_fork_repo


# ─────────────────────────────────────────────────────────────────────────────
# 1. UNIT — FORK path
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fork_path_emits_all_six_events():
    """
    FORK path: user has NO write access → fork → wait_for_fork_ready →
    branch → commit → PR.

    Verifies:
    - access_determined (FORK)
    - fork_created
    - fork_ready
    - branch_created
    - commit_created
    - pr_created
    - PullRequestResult.access_level == "FORK"
    - pr_url is the upstream PR URL (not the fork URL)
    - pr_head contains "testuser:" prefix
    - No GITHUB_TOKEN env fallback is required
    """
    UPSTREAM = "octocat/Hello-World"
    FORK = "testuser/Hello-World"
    BRANCH = "recovery/fix-inc12345-abc1234d"

    mock_github_class, mock_orig_repo, mock_fork_repo = _make_mock_repo(
        push=False,
        user_login="testuser",
        fork_full_name=FORK,
        pr_html_url=f"https://github.com/{UPSTREAM}/pull/42",
    )

    events: list[tuple[str, str, dict]] = []

    async def capture_event(event_type, message, metadata):
        events.append((event_type, message, metadata))

    with patch("backend.integrations.github_tools.Github", mock_github_class):
        gh = GitHubTools(_make_settings())
        result = await gh.create_recovery_pr_full(
            repository_full_name=UPSTREAM,
            branch_name=BRANCH,
            base_branch="main",
            file_path="calculator.py",
            content="def add(a, b): return a + b\n",
            commit_message="fix(calculator.py): add type safety",
            pr_title="fix(calculator.py): add type safety",
            pr_body="Automated recovery PR.",
            on_event=capture_event,
        )

    # ── Assertions: PullRequestResult ────────────────────────────────────
    assert result.access_level == "FORK", f"Expected FORK, got {result.access_level}"
    assert result.fork_repo == FORK
    assert result.reused is False
    assert result.pr_url == f"https://github.com/{UPSTREAM}/pull/42"
    assert result.pr_number == 42
    assert result.commit_sha == "committed999"
    assert result.branch_name == BRANCH

    # ── Assertions: create_pull was called on upstream with "testuser:branch" ──
    mock_orig_repo.create_pull.assert_called_once()
    call_kwargs = mock_orig_repo.create_pull.call_args[1]
    assert call_kwargs["head"] == f"testuser:{BRANCH}", (
        f"Expected head='testuser:{BRANCH}', got {call_kwargs['head']}"
    )
    assert call_kwargs["base"] == "main"

    # ── Assertions: fork was created ─────────────────────────────────────
    mock_github_class.return_value.get_user.return_value.create_fork.assert_called_once()

    # ── Assertions: branch was created on FORK, not upstream ─────────────
    mock_fork_repo.create_git_ref.assert_called_once()
    ref_call = mock_fork_repo.create_git_ref.call_args[1]
    assert ref_call["ref"] == f"refs/heads/{BRANCH}"

    # ── Assertions: SSE events sequence ──────────────────────────────────
    event_types = [e[0] for e in events]
    print(f"\n[FORK path] SSE events emitted: {event_types}")

    assert "access_determined" in event_types, "Missing access_determined"
    assert "fork_created" in event_types, "Missing fork_created"
    assert "fork_ready" in event_types, "Missing fork_ready"
    assert "branch_created" in event_types, "Missing branch_created"
    assert "commit_created" in event_types, "Missing commit_created"
    assert "pr_created" in event_types, "Missing pr_created"
    assert "pr_reused" not in event_types, "Should NOT have pr_reused"

    # Check order
    assert event_types.index("access_determined") < event_types.index("fork_created")
    assert event_types.index("fork_created") < event_types.index("fork_ready")
    assert event_types.index("fork_ready") < event_types.index("branch_created")
    assert event_types.index("branch_created") < event_types.index("commit_created")
    assert event_types.index("commit_created") < event_types.index("pr_created")

    # Check access_determined metadata
    access_evt = next(e for e in events if e[0] == "access_determined")
    assert access_evt[2]["access_level"] == "FORK"
    assert access_evt[2]["original_repo"] == UPSTREAM

    # Check fork_created metadata
    fork_evt = next(e for e in events if e[0] == "fork_created")
    assert fork_evt[2]["fork_repo"] == FORK
    assert fork_evt[2]["user_login"] == "testuser"

    # Check pr_created metadata
    pr_evt = next(e for e in events if e[0] == "pr_created")
    assert pr_evt[2]["pr_url"] == f"https://github.com/{UPSTREAM}/pull/42"
    assert pr_evt[2]["pr_number"] == 42
    assert pr_evt[2]["access_level"] == "FORK"
    assert pr_evt[2]["original_repo"] == UPSTREAM

    print("✅ FORK path — all 6 SSE events emitted in correct order with correct metadata.")


# ─────────────────────────────────────────────────────────────────────────────
# 2. UNIT — WRITE path
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_write_path_emits_three_events_no_fork():
    """
    WRITE path: user HAS write access → no fork → branch + commit + PR
    directly on original repo.

    Verifies:
    - access_determined (WRITE)
    - branch_created (on original repo)
    - commit_created
    - pr_created
    - NO fork_created / fork_ready
    """
    UPSTREAM = "myorg/my-repo"
    BRANCH = "recovery/fix-aaa11111-bbb22222"

    mock_github_class, mock_orig_repo, _ = _make_mock_repo(
        push=True,
        user_login="myuser",
        fork_full_name="myuser/my-repo",
        pr_html_url=f"https://github.com/{UPSTREAM}/pull/7",
        pr_number=7,
    )
    mock_orig_repo.get_contents.side_effect = UnknownObjectException(404, {"message": "Not Found"}, {})
    mock_orig_repo.create_file.return_value = {"commit": MagicMock(sha="sha777")}

    events: list[tuple] = []

    async def capture(event_type, message, metadata):
        events.append((event_type, message, metadata))

    with patch("backend.integrations.github_tools.Github", mock_github_class):
        gh = GitHubTools(_make_settings())
        result = await gh.create_recovery_pr_full(
            repository_full_name=UPSTREAM,
            branch_name=BRANCH,
            base_branch="main",
            file_path="src/auth.py",
            content="# fixed\n",
            commit_message="fix(auth.py): fix",
            pr_title="fix auth",
            pr_body="body",
            on_event=capture,
        )

    assert result.access_level == "WRITE"
    assert result.fork_repo == ""
    assert result.reused is False
    assert result.pr_number == 7

    event_types = [e[0] for e in events]
    print(f"\n[WRITE path] SSE events emitted: {event_types}")

    assert "access_determined" in event_types
    assert "branch_created" in event_types
    assert "commit_created" in event_types
    assert "pr_created" in event_types
    assert "fork_created" not in event_types
    assert "fork_ready" not in event_types
    assert "pr_reused" not in event_types

    access_evt = next(e for e in events if e[0] == "access_determined")
    assert access_evt[2]["access_level"] == "WRITE"

    print("✅ WRITE path — no fork events, correct SSE sequence.")


# ─────────────────────────────────────────────────────────────────────────────
# 3. UNIT — REUSE path (existing PR)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reuse_path_returns_existing_pr_without_creating_branch():
    """
    REUSE path: an open PR already exists for this branch.

    Verifies:
    - pr_reused event emitted
    - create_git_ref (branch creation) NOT called
    - create_file (commit) NOT called
    - create_pull (PR creation) NOT called
    - result.reused == True
    """
    UPSTREAM = "octocat/Hello-World"
    BRANCH = "recovery/fix-abc12345-def67890"

    existing_pr_mock = MagicMock()
    existing_pr_mock.html_url = f"https://github.com/{UPSTREAM}/pull/99"
    existing_pr_mock.number = 99

    mock_github_class, mock_orig_repo, _ = _make_mock_repo(
        push=True,
        existing_pulls=[existing_pr_mock],
        pr_number=99,
    )

    events: list[tuple] = []

    async def capture(event_type, message, metadata):
        events.append((event_type, message, metadata))

    with patch("backend.integrations.github_tools.Github", mock_github_class):
        gh = GitHubTools(_make_settings())
        result = await gh.create_recovery_pr_full(
            repository_full_name=UPSTREAM,
            branch_name=BRANCH,
            base_branch="main",
            file_path="file.py",
            content="x",
            commit_message="fix",
            pr_title="fix",
            pr_body="body",
            on_event=capture,
        )

    assert result.reused is True
    assert result.pr_number == 99
    assert "/pull/99" in result.pr_url

    mock_orig_repo.create_git_ref.assert_not_called()
    mock_orig_repo.create_file.assert_not_called()
    mock_orig_repo.create_pull.assert_not_called()

    event_types = [e[0] for e in events]
    print(f"\n[REUSE path] SSE events emitted: {event_types}")
    assert "pr_reused" in event_types
    assert "branch_created" not in event_types
    assert "fork_created" not in event_types

    print("✅ REUSE path — existing PR returned, no branch/commit/fork created.")


# ─────────────────────────────────────────────────────────────────────────────
# 4. UNIT — fork readiness timeout raises GitHubForkTimeoutError
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fork_timeout_raises_loudly():
    """
    If the fork never becomes ready within max_wait, GitHubForkTimeoutError
    must be raised immediately — no silent swallowing.
    """
    from github.GithubException import GithubException as PyGithubException

    UPSTREAM = "octocat/Hello-World"
    FORK = "testuser/Hello-World"

    mock_github_class, mock_orig_repo, mock_fork_repo = _make_mock_repo(
        push=False,
        fork_full_name=FORK,
    )
    # Fork never becomes ready
    mock_fork_repo.get_branch.side_effect = PyGithubException(404, "not found")

    with patch("backend.integrations.github_tools.Github", mock_github_class):
        gh = GitHubTools(_make_settings())
        with pytest.raises(GitHubForkTimeoutError):
            await gh.wait_for_fork_ready(
                FORK,
                "main",
                poll_interval=0.05,   # fast for test
                max_wait=0.2,         # short deadline
            )

    print("✅ Fork timeout — GitHubForkTimeoutError raised correctly.")


# ─────────────────────────────────────────────────────────────────────────────
# 5. UNIT — no GITHUB_TOKEN fallback; fails loudly with bad token
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_github_token_env_fallback():
    """
    Verify that GitHubTools uses only the token passed in GitHubSettings.
    If that token is invalid (non-real) the GitHub API call fails loudly;
    GITHUB_TOKEN env is NOT used as a fallback.
    """
    from github.GithubException import GithubException as PyGithubException

    mock_github_class = MagicMock()
    mock_client = MagicMock()
    mock_github_class.return_value = mock_client
    mock_client.get_repo.side_effect = PyGithubException(401, "Bad credentials")

    token_used: list[str] = []

    original_init = GitHubTools.__init__

    def tracking_init(self, settings):
        token_used.append(settings.token)
        original_init(self, settings)

    with patch("backend.integrations.github_tools.Github", mock_github_class):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "env_token_must_not_be_used"}):
            gh = GitHubTools(GitHubSettings(token="state_oauth_token"))
            with pytest.raises(GitHubRepositoryError):
                gh.check_write_access("octocat/Hello-World")

    # Verify the token used was the one from GitHubSettings, not env
    init_call = mock_github_class.call_args
    used_token = init_call[1].get("login_or_token") or (getattr(init_call[1].get("auth"), "token", None) if init_call[1].get("auth") else None) or (init_call[0][0] if init_call[0] else None)
    assert used_token == "state_oauth_token", (
        f"Expected 'state_oauth_token' to be used, got: {init_call}"
    )
    print("✅ No GITHUB_TOKEN env fallback — only state OAuth token used.")


# ─────────────────────────────────────────────────────────────────────────────
# 6. LIVE — real GitHub API, read-only public repo
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("GITHUB_TOKEN"),
    reason="GITHUB_TOKEN not set; skipping live test",
)
async def test_live_check_write_access_public_repo():
    """
    Live test: verify check_write_access() against a well-known public repo
    (octocat/Hello-World) that the token owner almost certainly cannot push to.

    This validates:
    - The OAuth token reaches the GitHub API.
    - permissions.push correctly returns False for a non-collaborator.
    - No GITHUB_TOKEN env fallback needed.
    """
    token = os.environ["GITHUB_TOKEN"]
    gh = GitHubTools(GitHubSettings(token=token))

    user_login = gh.get_authenticated_user_login()
    print(f"\n[LIVE] Authenticated as: {user_login}")

    has_write = gh.check_write_access("octocat/Hello-World")
    print(f"[LIVE] check_write_access('octocat/Hello-World') = {has_write}")

    # For any real user token, this should be False (octocat/Hello-World is
    # a maintained public repo not granting push to random OAuth tokens)
    assert has_write is False, (
        f"Unexpected WRITE access to octocat/Hello-World for user '{user_login}'. "
        "If you are octocat, use a different test repo."
    )

    print(f"✅ LIVE: {user_login} has NO WRITE access to octocat/Hello-World → FORK path would be taken.")


if __name__ == "__main__":
    asyncio.run(test_fork_path_emits_all_six_events())
    asyncio.run(test_write_path_emits_three_events_no_fork())
    asyncio.run(test_reuse_path_returns_existing_pr_without_creating_branch())
    asyncio.run(test_fork_timeout_raises_loudly())
    asyncio.run(test_no_github_token_env_fallback())
    print("\n✅ ALL UNIT TESTS PASSED")
