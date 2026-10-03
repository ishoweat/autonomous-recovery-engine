import hmac
import hashlib
import json
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from backend.main import app
from backend.db.base import Base
from backend.db.session import get_db
from backend.services.github_webhook import verify_github_signature, parse_github_webhook
import os
from backend.config import get_settings

def sign_payload(payload_bytes: bytes, secret: str = None) -> str:
    secret = secret or get_settings().github_webhook_secret
    digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_client():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_health_check(async_client):
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_signature_verification():
    secret = "secret-key-123"
    payload = b'{"test": "data"}'
    expected_digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    signature_header = f"sha256={expected_digest}"

    assert verify_github_signature(
        payload=payload,
        signature_header=signature_header,
        secret=secret
    ) is True

    assert verify_github_signature(
        payload=payload,
        signature_header="sha256=invaliddigest1234567890123456789012345678901234567890123456789012",
        secret=secret
    ) is False


def test_webhook_parsing():
    payload = {
        "action": "completed",
        "conclusion": "failure",
        "ref": "refs/heads/feature-auth",
        "repository": {"full_name": "acme/backend-service", "default_branch": "main"},
        "sender": {"login": "octocat"},
        "commits": [{"added": ["backend/api/auth.py"]}]
    }
    parsed = parse_github_webhook(event_name="workflow_run", payload=payload)
    assert parsed.repository == "acme/backend-service"
    assert parsed.branch == "feature-auth"
    assert parsed.is_failure_event is True
    assert "backend/api/auth.py" in parsed.affected_files


@pytest.mark.asyncio
async def test_webhook_endpoint_and_get_incident(async_client, monkeypatch):
    from backend.config import get_settings
    monkeypatch.setattr(get_settings(), "allow_mock_mode", True)
    payload = {
        "action": "completed",
        "conclusion": "failure",
        "ref": "refs/heads/main",
        "repository": {"full_name": "acme/backend-service"},
        "sender": {"login": "octocat"}
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = {
        "X-GitHub-Event": "workflow_run",
        "X-Recovery-Mock": "true",
        "X-Hub-Signature-256": sign_payload(body_bytes)
    }
    response = await async_client.post("/webhook/github", content=body_bytes, headers=headers)
    assert response.status_code == 202
    res_data = response.json()
    assert res_data["accepted"] is True
    incident_id = res_data["incident_id"]

    # Fetch incident state
    get_res = await async_client.get(f"/api/v1/incident/{incident_id}")
    assert get_res.status_code == 200
    inc_data = get_res.json()
    assert inc_data["incident_id"] == incident_id
    assert inc_data["repository"] == "acme/backend-service"
    assert inc_data["is_mock_mode"] is True
    assert inc_data["status"] == "received"


@pytest.mark.asyncio
async def test_approval_endpoint_state_gate(async_client):
    # Create incident directly
    payload = {
        "action": "completed",
        "conclusion": "failure",
        "ref": "refs/heads/main",
        "repository": {"full_name": "acme/backend-service"},
        "sender": {"login": "octocat"}
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = {
        "X-GitHub-Event": "workflow_run",
        "X-Recovery-Mock": "true",
        "X-Hub-Signature-256": sign_payload(body_bytes)
    }
    res = await async_client.post("/webhook/github", content=body_bytes, headers=headers)
    incident_id = res.json()["incident_id"]

    # Attempt approval while status is 'received' (should fail with 409 Conflict)
    app_res = await async_client.post(
        f"/api/v1/incident/{incident_id}/approve",
        json={"approved": True, "reviewer": "admin", "reason": "Looks good"}
    )
    assert app_res.status_code == 409
    assert "not awaiting human approval" in app_res.json()["detail"]
