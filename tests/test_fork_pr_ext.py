"""
test_fork_pr_ext.py — Unit tests for Phase 10 extension module (recovery_ext/fork_pr.py).
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch

from backend.recovery_ext.fork_pr import (
    AccessLevel,
    classify_repo_access,
    check_ai_recovery_opt_out,
    get_pr_template_content,
    sync_stale_fork,
    record_fork_consent,
    check_fork_consent,
    is_repo_allowed_in_demo_mode,
    poll_fork_pr_status,
)


@pytest.mark.asyncio
async def test_consent_db_record_and_check(tmp_path):
    db_file = str(tmp_path / "test_consent.db")
    user_id = "user_123"
    repo = "owner/public-repo"

    assert await check_fork_consent(user_id, repo, db_path=db_file) is False
    await record_fork_consent(user_id, repo, db_path=db_file)
    assert await check_fork_consent(user_id, repo, db_path=db_file) is True


def test_classify_repo_access_archived():
    mock_repo = MagicMock()
    mock_repo.archived = True

    mock_gh = MagicMock()
    mock_gh.get_repo.return_value = mock_repo

    with patch("github.Github", return_value=mock_gh):
        level, meta = classify_repo_access("owner/archived-repo", "token123")
        assert level == AccessLevel.ARCHIVED


def test_classify_repo_access_forking_disabled():
    mock_repo = MagicMock()
    mock_repo.archived = False
    mock_repo.private = False
    mock_repo.allow_forking = False

    mock_gh = MagicMock()
    mock_gh.get_repo.return_value = mock_repo

    with patch("github.Github", return_value=mock_gh):
        level, meta = classify_repo_access("owner/no-fork-repo", "token123")
        assert level == AccessLevel.FORKING_DISABLED


def test_classify_repo_access_owner_write():
    mock_repo = MagicMock()
    mock_repo.archived = False
    mock_repo.private = False
    mock_repo.allow_forking = True
    mock_repo.permissions.push = True

    mock_gh = MagicMock()
    mock_gh.get_repo.return_value = mock_repo

    with patch("github.Github", return_value=mock_gh):
        level, meta = classify_repo_access("owner/my-repo", "token123")
        assert level == AccessLevel.OWNER_WRITE


def test_classify_repo_access_fork_required():
    mock_repo = MagicMock()
    mock_repo.archived = False
    mock_repo.private = False
    mock_repo.allow_forking = True
    mock_repo.permissions.push = False

    mock_gh = MagicMock()
    mock_gh.get_repo.return_value = mock_repo

    with patch("github.Github", return_value=mock_gh):
        level, meta = classify_repo_access("owner/other-repo", "token123")
        assert level == AccessLevel.FORK_REQUIRED


def test_demo_mode_allowlist():
    with patch.dict(os.environ, {"PUBLIC_DEMO_ALLOWLIST": "octocat/Hello-World,Sahil707-pop/autonomous-recovery-engine"}):
        assert is_repo_allowed_in_demo_mode("octocat/Hello-World") is True
        assert is_repo_allowed_in_demo_mode("sahil707-pop/autonomous-recovery-engine") is True
        assert is_repo_allowed_in_demo_mode("random/unknown-repo") is False
