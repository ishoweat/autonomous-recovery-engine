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
