import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.mark.asyncio
async def test_github_tree_endpoint():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/github/tree",
            json={
                "repository_url": "https://github.com/demo/autonomous-recovery-engine",
                "branch": "main",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["owner"] == "demo"
        assert data["repo"] == "autonomous-recovery-engine"
        assert len(data["tree"]) > 0
        assert any(item["path"] == "backend/api/auth.py" for item in data["tree"])


@pytest.mark.asyncio
async def test_github_file_content_endpoint():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/github/file-content",
            json={
                "repository_url": "https://github.com/demo/autonomous-recovery-engine",
                "file_path": "backend/api/auth.py",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["file_path"] == "backend/api/auth.py"
        assert "payload[\"user_id\"]" in data["content"]
        assert data["language"] == "python"


@pytest.mark.asyncio
async def test_github_create_pr_endpoint():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"github_token": "test-token"},
    ) as client:
        response = await client.post(
            "/api/v1/github/create-pr",
            json={
                "incident_id": "test-pr-inc-1",
                "repository_url": "https://github.com/demo/autonomous-recovery-engine",
                "file_path": "backend/api/auth.py",
                "corrected_code": "def authenticate(payload):\n    return lookup_user(payload.get('user_id'))\n",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "pr_url" in data
        assert "pull" in data["pr_url"]
        assert data["pr_number"] > 0
        assert data["merged"] is False
        assert data["merge_mode"] == "manual"


@pytest.mark.asyncio
async def test_github_create_pr_auto_merge_true():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"github_token": "test-token"},
    ) as client:
        response = await client.post(
            "/api/v1/github/create-pr",
            json={
                "incident_id": "test-pr-inc-auto",
                "repository_url": "https://github.com/demo/autonomous-recovery-engine",
                "file_path": "backend/api/auth.py",
                "corrected_code": "def authenticate(payload):\n    return lookup_user(payload.get('user_id'))\n",
                "auto_merge": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["merged"] is True
        assert data["merge_mode"] == "auto"
        assert data["commit_sha"] is not None


@pytest.mark.asyncio
async def test_github_create_pr_auto_merge_false_explicit():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"github_token": "test-token"},
    ) as client:
        response = await client.post(
            "/api/github/create-pr",
            json={
                "incident_id": "test-pr-inc-manual",
                "repo": "demo/autonomous-recovery-engine",
                "filePath": "backend/api/auth.py",
                "fixedContent": "def authenticate(payload):\n    return lookup_user(payload.get('user_id'))\n",
                "auto_merge": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["merged"] is False
        assert data["merge_mode"] == "manual"
        assert data["merge_sha"] is None


@pytest.mark.asyncio
async def test_github_create_pr_branch_collision_retry(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    import httpx
    from backend.api.github_workspace import create_pr_endpoint, CreatePrRequest

    call_count = {"create_ref": 0, "merge": 0}

    async def mock_handler(request: httpx.Request):
        url_str = str(request.url)
        if "/git/ref/heads/" in url_str:
            return httpx.Response(200, json={"object": {"sha": "base-sha-123"}})
        elif "/git/refs" in url_str and request.method == "POST":
            call_count["create_ref"] += 1
            if call_count["create_ref"] == 1:
                # First attempt collides
                return httpx.Response(422, text='{"message": "Reference already exists"}')
            # Second attempt with suffix succeeds
            return httpx.Response(201, json={"ref": "refs/heads/ai-recovery/test", "object": {"sha": "base-sha-123"}})
        elif "/contents/" in url_str:
            return httpx.Response(200, json={"sha": "existing-sha", "commit": {"sha": "commit-sha-456"}})
        elif "/pulls" in url_str and request.method == "POST":
            return httpx.Response(201, json={"number": 42, "html_url": "https://github.com/test-owner/test-repo/pull/42"})
        elif "/pulls/42/merge" in url_str and request.method == "PUT":
            call_count["merge"] += 1
            return httpx.Response(200, json={"sha": "merge-sha-789", "merged": True, "message": "Pull Request successfully merged"})
        return httpx.Response(404)

    mock_transport = httpx.MockTransport(mock_handler)
    original_async_client = httpx.AsyncClient

    def custom_async_client(*args, **kwargs):
        kwargs["transport"] = mock_transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", custom_async_client)

    # Test auto_merge=False
    req_manual = CreatePrRequest(
        repo="test-owner/test-repo",
        filePath="test.py",
        fixedContent="print('hello')",
        auto_merge=False,
    )
    res_manual = await create_pr_endpoint(
        request=req_manual,
        session=None,
        github_token="ghp_dummytoken123",
    )
    assert res_manual.merged is False
    assert res_manual.merge_mode == "manual"
    assert res_manual.pr_number == 42
    assert call_count["merge"] == 0
    assert call_count["create_ref"] == 2  # Proves duplicate was caught and retried with suffix!

    # Reset and test auto_merge=True
    call_count["create_ref"] = 1  # will succeed on first try now since it will be retry logic or direct
    req_auto = CreatePrRequest(
        repo="test-owner/test-repo",
        filePath="test.py",
        fixedContent="print('hello')",
        auto_merge=True,
    )
    res_auto = await create_pr_endpoint(
        request=req_auto,
        session=None,
        github_token="ghp_dummytoken123",
    )
    assert res_auto.merged is True
    assert res_auto.merge_mode == "auto"
    assert res_auto.merge_sha == "merge-sha-789"
    assert call_count["merge"] == 1

