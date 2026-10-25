"""
test_fork_pr_api.py — API tests for Phase 10 access-check and consent endpoints.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_access_check_endpoint():
    mock_meta = {"full_name": "octocat/Hello-World", "private": False}
    with patch("backend.recovery_ext.fork_pr.classify_repo_access") as mock_classify:
        from backend.recovery_ext.fork_pr import AccessLevel
        mock_classify.return_value = (AccessLevel.FORK_REQUIRED, mock_meta)
        with patch("backend.recovery_ext.fork_pr.check_ai_recovery_opt_out", return_value=False):
            response = client.get("/api/v1/github/access-check?repo=octocat/Hello-World")
            assert response.status_code == 200
            data = response.json()
            assert data["repository"] == "octocat/Hello-World"
            assert data["access_level"] == "FORK_REQUIRED"
            assert data["requires_consent"] is True
            assert data["opted_out"] is False


def test_consent_record_endpoint():
    response = client.post(
        "/api/v1/github/consent",
        json={"repository": "octocat/Hello-World"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["repository"] == "octocat/Hello-World"
