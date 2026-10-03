from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from github.GithubException import GithubException
from httpx import ASGITransport, AsyncClient

from backend.config.github_config import GitHubSettings
from backend.db.models import Incident, IncidentStatus
from backend.db.session import AsyncSessionLocal
from backend.integrations.github_tools import (
    GitHubForkTimeoutError,
    GitHubIntegrationError,
    GitHubRepositoryError,
    GitHubTools,
    PullRequestResult,
)
from backend.main import app
from backend.orchestration.runtime import recovery_runtime
from backend.orchestration.state import RecoveryState
from backend.orchestration.state_factory import create_initial_recovery_state
from backend.services.github_webhook import verify_github_signature
from backend.services.incidents import create_incident, get_incident, update_incident_state
from backend.services.session_service import session_service
from backend.services.telemetry import telemetry_manager


@pytest.mark.asyncio
async def test_verification_1_write_repository():
    """
    VERIFICATION 1: WRITE repository.
    Authenticated user has push permission:
    user repository -> recovery branch -> verified commit -> PR
    Emits: access_determined (WRITE) -> branch_created -> commit_created -> pr_created
    """
    settings = GitHubSettings(token="gho_oauth_write_user_token_abc")
    tools = GitHubTools(settings)

    events: list[tuple[str, str, dict]] = []

    async def event_collector(event_type: str, message: str, metadata: dict):
        events.append((event_type, message, metadata))

    mock_repo = MagicMock()
    mock_repo.full_name = "testuser/my-repo"
    mock_repo.permissions = MagicMock()
    mock_repo.permissions.push = True  # WRITE ACCESS
    mock_repo.get_pulls.return_value = []
    mock_repo.get_branch.return_value.commit.sha = "base_sha_12345"
    mock_repo.create_git_ref.return_value = None
    mock_repo.get_contents.return_value.sha = "old_file_sha"
    mock_repo.update_file.return_value = {
        "commit": MagicMock(sha="verified_commit_sha_write_999")
    }

    mock_pull = MagicMock()
    mock_pull.html_url = "https://github.com/testuser/my-repo/pull/1"
    mock_pull.number = 1
    mock_repo.create_pull.return_value = mock_pull

    with patch.object(tools.client, "get_repo", return_value=mock_repo), \
         patch.object(tools.client, "get_user", return_value=MagicMock(login="testuser")):

        branch_name = "recovery/fix-write-path-001"
        result = await tools.create_recovery_pr_full(
            repository_full_name="testuser/my-repo",
            branch_name=branch_name,
            base_branch="main",
            file_path="src/service.py",
            content="def run(): return True",
            commit_message="fix(src/service.py): patch applied",
            pr_title="fix: resolve service failure",
            pr_body="Automated recovery fix",
            on_event=event_collector,
        )

        assert isinstance(result, PullRequestResult)
        assert result.access_level == "WRITE"
        assert result.fork_repo == ""
        assert result.branch_name == branch_name
        assert result.commit_sha == "verified_commit_sha_write_999"
        assert result.pr_url == "https://github.com/testuser/my-repo/pull/1"
        assert result.pr_number == 1
        assert result.reused is False

        event_types = [e[0] for e in events]
        assert event_types == [
            "access_determined",
            "branch_created",
            "commit_created",
            "pr_created",
        ]
        assert events[0][2]["access_level"] == "WRITE"
        assert events[1][2]["target_repo"] == "testuser/my-repo"
        assert events[2][2]["commit_sha"] == "verified_commit_sha_write_999"

        # Verify PR creation on target repo with direct branch head
        mock_repo.create_pull.assert_called_once_with(
            title="fix: resolve service failure",
            body="Automated recovery fix",
            head=branch_name,
            base="main",
        )


@pytest.mark.asyncio
async def test_verification_2_no_write_public_repository_oauth():
    """
    VERIFICATION 2: NO-WRITE public repository using OAuth.
    Authenticated user has read-only access (no push):
    public upstream repository -> user's fork -> wait for fork readiness ->
    recovery branch in fork -> verified commit in fork -> PR from fork:branch to upstream.
    Emits: access_determined (FORK) -> fork_created -> fork_ready -> branch_created -> commit_created -> pr_created
    """
    settings = GitHubSettings(token="gho_oauth_nowrite_user_token_xyz")
    tools = GitHubTools(settings)

    events: list[tuple[str, str, dict]] = []

    async def event_collector(event_type: str, message: str, metadata: dict):
        events.append((event_type, message, metadata))

    mock_upstream_repo = MagicMock()
    mock_upstream_repo.full_name = "public-org/public-tool"
    mock_upstream_repo.permissions = MagicMock()
    mock_upstream_repo.permissions.push = False  # NO WRITE ACCESS
    mock_upstream_repo.get_pulls.return_value = []

    mock_fork_repo = MagicMock()
    mock_fork_repo.full_name = "dev-contributor/public-tool"
    mock_fork_repo.get_branch.return_value.commit.sha = "fork_base_sha_555"
    mock_fork_repo.create_git_ref.return_value = None
    mock_fork_repo.get_contents.return_value.sha = "existing_fork_file_sha"
    mock_fork_repo.update_file.return_value = {
        "commit": MagicMock(sha="verified_fork_commit_sha_888")
    }

    mock_user = MagicMock()
    mock_user.login = "dev-contributor"
    mock_user.create_fork.return_value = mock_fork_repo

    mock_pull = MagicMock()
    mock_pull.html_url = "https://github.com/public-org/public-tool/pull/50"
    mock_pull.number = 50
    mock_upstream_repo.create_pull.return_value = mock_pull

    def get_repo_side_effect(name):
        if name == "public-org/public-tool":
            return mock_upstream_repo
        if name == "dev-contributor/public-tool":
            return mock_fork_repo
        raise GitHubRepositoryError(f"Unknown repo {name}")

    with patch.object(tools.client, "get_repo", side_effect=get_repo_side_effect), \
         patch.object(tools.client, "get_user", return_value=mock_user):

        branch_name = "recovery/fix-upstream-bug-42"
        result = await tools.create_recovery_pr_full(
            repository_full_name="public-org/public-tool",
            branch_name=branch_name,
            base_branch="main",
            file_path="src/parser.py",
            content="def parse(): return {'status': 'ok'}",
            commit_message="fix(parser): handle syntax error",
            pr_title="fix: handle parser failure",
            pr_body="Cross-repository fork recovery PR",
            on_event=event_collector,
        )

        assert isinstance(result, PullRequestResult)
        assert result.access_level == "FORK"
        assert result.fork_repo == "dev-contributor/public-tool"
        assert result.branch_name == branch_name
        assert result.commit_sha == "verified_fork_commit_sha_888"
        assert result.pr_url == "https://github.com/public-org/public-tool/pull/50"
        assert result.pr_number == 50
        assert result.reused is False

        event_types = [e[0] for e in events]
        assert event_types == [
            "access_determined",
            "fork_created",
            "fork_ready",
            "branch_created",
            "commit_created",
            "pr_created",
        ]
        assert events[0][2]["access_level"] == "FORK"
        assert events[1][2]["fork_repo"] == "dev-contributor/public-tool"
        assert events[3][2]["target_repo"] == "dev-contributor/public-tool"

        # Verify cross-repo PR call has user:branch as head
        mock_upstream_repo.create_pull.assert_called_once_with(
            title="fix: handle parser failure",
            body="Cross-repository fork recovery PR",
            head="dev-contributor:" + branch_name,
            base="main",
        )


@pytest.mark.asyncio
async def test_verification_3_existing_pr_deduplication_and_reuse():
    """
    VERIFICATION 3: Existing PR deduplication.
    Before creating a branch/PR:
    1. Checks whether recovery PR already exists.
    2. Returns/reuses it immediately without creating duplicate branch or PR.
    3. Emits pr_reused event with commit SHA and metadata.
    """
    settings = GitHubSettings(token="gho_oauth_reuse_token_111")
    tools = GitHubTools(settings)

    events: list[tuple[str, str, dict]] = []

    async def event_collector(event_type: str, message: str, metadata: dict):
        events.append((event_type, message, metadata))

    mock_existing_pr = MagicMock()
    mock_existing_pr.html_url = "https://github.com/org/repo/pull/77"
    mock_existing_pr.number = 77
    mock_existing_pr.head.sha = "existing_pr_head_sha_77777"

    mock_repo = MagicMock()
    mock_repo.full_name = "org/repo"
    # When querying open PRs matching branch_name, returns existing PR
    mock_repo.get_pulls.return_value = [mock_existing_pr]

    with patch.object(tools.client, "get_repo", return_value=mock_repo):
        branch_name = "recovery/existing-branch-fix"
        result = await tools.create_recovery_pr_full(
            repository_full_name="org/repo",
            branch_name=branch_name,
            base_branch="main",
            file_path="src/index.js",
            content="console.log('fixed');",
            commit_message="fix",
            pr_title="fix",
            pr_body="fix",
            on_event=event_collector,
        )

        assert result.reused is True
        assert result.pr_url == "https://github.com/org/repo/pull/77"
        assert result.pr_number == 77
        assert result.commit_sha == "existing_pr_head_sha_77777"

        # Verify NO branch or PR creation was called on repository
        mock_repo.create_git_ref.assert_not_called()
        mock_repo.create_pull.assert_not_called()

        event_types = [e[0] for e in events]
        assert event_types == ["pr_reused"]
        assert events[0][2]["reused"] is True
        assert events[0][2]["pr_number"] == 77
        assert events[0][2]["commit_sha"] == "existing_pr_head_sha_77777"


@pytest.mark.asyncio
async def test_verification_4_fork_readiness_delay():
    """
    VERIFICATION 4: Fork readiness delay.
    Tests bounded polling retry for fork readiness.
    Probes initially fail (simulating GitHub propagation lag), then succeed.
    Verifies that timeout raises GitHubForkTimeoutError if limit exceeded.
    """
    settings = GitHubSettings(token="gho_oauth_token_probe")
    tools = GitHubTools(settings)

    events: list[tuple[str, str, dict]] = []

    async def event_collector(event_type: str, message: str, metadata: dict):
        events.append((event_type, message, metadata))

    mock_fork_repo = MagicMock()
    # First 2 probes fail with GitHubException (branch not yet cloned), 3rd succeeds
    mock_fork_repo.get_branch.side_effect = [
        GithubException(404, "Branch not found yet", None),
        GithubException(404, "Branch not found yet", None),
        MagicMock(),
    ]

    with patch.object(tools.client, "get_repo", return_value=mock_fork_repo):
        await tools.wait_for_fork_ready(
            fork_full_name="user/forked-repo",
            base_branch="main",
            poll_interval=0.05,
            max_wait=2.0,
            on_event=event_collector,
        )

        assert len(events) == 1
        assert events[0][0] == "fork_ready"
        assert events[0][2]["probes"] == 3
        assert events[0][2]["fork_repo"] == "user/forked-repo"

    # Test timeout failure
    mock_timeout_repo = MagicMock()
    mock_timeout_repo.get_branch.side_effect = GithubException(404, "Still not ready", None)

    with patch.object(tools.client, "get_repo", return_value=mock_timeout_repo):
        with pytest.raises(GitHubForkTimeoutError) as exc_info:
            await tools.wait_for_fork_ready(
                fork_full_name="user/timeout-repo",
                base_branch="main",
                poll_interval=0.05,
                max_wait=0.15,
            )
        assert "did not become ready within" in str(exc_info.value)


@pytest.mark.asyncio
async def test_verification_5_github_api_failure_fails_loudly():
    """
    VERIFICATION 5: GitHub API failure.
    Real failures must fail loudly without simulation or silent fake success.
    """
    settings = GitHubSettings(token="gho_oauth_token_fail")
    tools = GitHubTools(settings)

    with patch.object(
        tools.client,
        "get_repo",
        side_effect=GithubException(403, "API rate limit exceeded for user", None),
    ):
        with pytest.raises(GitHubRepositoryError) as exc_info:
            tools.check_write_access("any-org/any-repo")

        assert "Unable to access GitHub repository" in str(exc_info.value)
        assert "403" in str(exc_info.value)


@pytest.mark.asyncio
async def test_verification_6_invalid_authorization_and_user_isolation():
    """
    VERIFICATION 6: Invalid/missing authorization & multi-user isolation.
    1. Pipeline refuses global GITHUB_TOKEN fallback when an authenticated user session is active.
    2. User A cannot view User B's incident state (403 Forbidden).
    3. User A cannot approve User B's incident (403 Forbidden).
    4. Tampered webhook signature fails with 401 Unauthorized.
    """
    # 1. Pipeline disallows global GITHUB_TOKEN fallback for user session
    from backend.orchestration.nodes import recovery_complete_node

    mock_llm = MagicMock()
    state_user_no_token: RecoveryState = {
        "incident_id": f"inc_iso_{uuid.uuid4().hex[:8]}",
        "repository_owner": "userA",
        "repository_name": "repoA",
        "repository_full_name": "userA/repoA",
        "repository_url": "https://github.com/userA/repoA",
        "default_branch": "main",
        "source_branch": "main",
        "commit_sha": "abc123456789",
        "runtime_model": "test-model",
        "failure_file": "app.py",
        "failure_line": 10,
        "error_message": "Error",
        "stack_trace": "",
        "github_payload": {},
        "is_mock_mode": False,
        "triage_context": "",
        "root_cause_analysis": {},
        "explainable_risk": {"score": 0.2, "decision": "ALLOW"},
        "action_decision": "ALLOW",
        "human_approved": True,
        "current_patch_diff": "diff",
        "test_results": {"exit_code": 0, "tests_passed": True},
        "retry_count": 0,
        "pr_url": "",
        "fork_repo": "",
        "user_id": "1001",
        "username": "userA",
        "session_id": "sess_non_existent_123",
        "user_oauth_token": "",  # Missing token for user session
        "similar_past_cases": [],
        "learning_confidence_boost": 0.0,
        "patch_explanation": "",
        "generated_test_code": "",
        "is_shadow_mode": False,
        "source_files": {},
        "polyglot_language": "python",
        "polyglot_audiences": {},
        "adversarial_report": {},
    }

    # Even if GITHUB_TOKEN is set in environment, user session must NOT fall back to it
    with patch.dict(os.environ, {"GITHUB_TOKEN": "global_fallback_token_prohibited"}):
        res = await recovery_complete_node(state_user_no_token, llm=mock_llm)
        assert res.get("recovery_failed") is True
        assert "Fallback to global GITHUB_TOKEN is prohibited" in res.get("error", "")

    # 2. Multi-user session setup
    sess_a = await session_service.create_session(
        {"id": 801, "login": "alice", "name": "Alice"},
        access_token="gho_alice_token_secret",
    )
    sess_b = await session_service.create_session(
        {"id": 802, "login": "bob", "name": "Bob"},
        access_token="gho_bob_token_secret",
    )

    inc_alice_id = f"inc_alice_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        await create_incident(
            session=db,
            incident_id=inc_alice_id,
            github_payload={"test": True},
            repository="alice/private-repo",
            branch="main",
            commit_sha="c1c2c3c4",
            is_mock_mode=False,
            user_id="801",
            username="alice",
            repository_owner="alice",
            repository_name="private-repo",
            repository_full_name="alice/private-repo",
        )
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Bob tries to view Alice's incident -> MUST return 403 Forbidden
        headers_bob = {"Authorization": f"Bearer {sess_b['session_id']}"}
        resp = await client.get(f"/api/v1/incident/{inc_alice_id}", headers=headers_bob)
        assert resp.status_code == 403, f"Expected 403 Forbidden for cross-user view, got: {resp.status_code}"
        assert "Access denied" in resp.json()["detail"]

        # Bob tries to approve Alice's incident -> MUST return 403 Forbidden
        resp_approve = await client.post(
            f"/api/v1/incident/{inc_alice_id}/approve",
            json={"approved": True, "reviewer": "bob"},
            headers=headers_bob,
        )
        assert resp_approve.status_code == 403, f"Expected 403 Forbidden for cross-user approval, got: {resp_approve.status_code}"
        assert "Access denied" in resp_approve.json()["detail"]

        # Alice herself can access her incident -> 200 OK
        headers_alice = {"Authorization": f"Bearer {sess_a['session_id']}"}
        resp_alice = await client.get(f"/api/v1/incident/{inc_alice_id}", headers=headers_alice)
        assert resp_alice.status_code == 200
        assert resp_alice.json()["incident_id"] == inc_alice_id

    # 3. Webhook signature tampering verification
    webhook_payload = b'{"action": "completed", "repository": {"full_name": "owner/repo"}}'
    valid_secret = "correct_webhook_secret_key_456"
    assert verify_github_signature(
        payload=webhook_payload,
        signature_header="sha256=invalid_tampered_signature_hash_00000000000000000000000000000000",
        secret=valid_secret,
    ) is False
