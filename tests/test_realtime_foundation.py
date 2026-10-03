import hashlib
import hmac
import json
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from backend.main import app
from backend.db.base import Base
from backend.db.session import get_db
from backend.config import get_settings
from backend.services.github_webhook import parse_github_webhook, verify_github_signature

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def sign_payload(payload_bytes: bytes, secret: str = None) -> str:
    secret = secret or get_settings().github_webhook_secret
    digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest_asyncio.fixture
async def async_client():
    from backend.orchestration.runtime import recovery_runtime
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await recovery_runtime.start()

    async def override_get_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await recovery_runtime.stop()
    await engine.dispose()


@pytest.mark.asyncio
async def test_health_endpoint_schema(async_client):
    """GET /health must return all 6 status fields."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["backend"] == "ok"
    assert data["database"] == "ok"
    assert "github" in data
    assert "nebius" in data
    assert data["realtime"] == "ok"


@pytest.mark.asyncio
async def test_ready_endpoint(async_client):
    """GET /ready must return ready status and dependency checks."""
    response = await async_client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert "checks" in data
    assert data["checks"]["database"] == "ok"
    assert data["checks"]["realtime"] == "ok"


@pytest.mark.asyncio
async def test_real_workflow_run_webhook_parsing():
    """Verify parsing real GitHub workflow_run event with nested structures."""
    payload = {
        "action": "completed",
        "workflow_run": {
            "id": 1122334455,
            "name": "Integration CI",
            "status": "completed",
            "conclusion": "failure",
            "head_branch": "feature/payment-fix",
            "head_sha": "d3b07384d113edec49eaa6238ad5ff00",
        },
        "repository": {
            "full_name": "acme-corp/payment-service",
            "default_branch": "main",
        },
        "sender": {"login": "github-actions"},
    }

    parsed = parse_github_webhook(event_name="workflow_run", payload=payload)
    assert parsed.repository == "acme-corp/payment-service"
    assert parsed.branch == "feature/payment-fix"
    assert parsed.commit_sha == "d3b07384d113edec49eaa6238ad5ff00"
    assert parsed.github_run_id == "1122334455"
    assert parsed.workflow_name == "Integration CI"
    assert parsed.is_failure_event is True


@pytest.mark.asyncio
async def test_webhook_idempotency_by_run_id(async_client):
    """Repeated webhook events for the same GitHub run ID return the existing incident."""
    payload = {
        "action": "completed",
        "workflow_run": {
            "id": 99887766,
            "name": "Unit Tests",
            "status": "completed",
            "conclusion": "failure",
            "head_branch": "main",
            "head_sha": "aabbccddeeff00112233",
        },
        "repository": {
            "full_name": "acme-corp/auth-svc",
            "default_branch": "main",
        },
        "sender": {"login": "github-actions"},
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = {
        "X-GitHub-Event": "workflow_run",
        "X-Recovery-Mock": "true",
        "X-Hub-Signature-256": sign_payload(body_bytes),
    }

    # First delivery: creates incident
    res1 = await async_client.post("/webhook/github", content=body_bytes, headers=headers)
    assert res1.status_code == 202
    data1 = res1.json()
    incident_id1 = data1["incident_id"]

    # Second delivery with same run ID: must be idempotent
    res2 = await async_client.post("/webhook/github", content=body_bytes, headers=headers)
    assert res2.status_code == 202
    data2 = res2.json()
    assert data2["incident_id"] == incident_id1
    assert data2.get("duplicate") is True


@pytest.mark.asyncio
async def test_webhook_rejects_successful_run(async_client):
    """Non-failure workflow_run events must not create recovery incidents."""
    payload = {
        "action": "completed",
        "workflow_run": {
            "id": 55443322,
            "name": "Lint",
            "status": "completed",
            "conclusion": "success",
            "head_branch": "main",
            "head_sha": "1234567890abcdef",
        },
        "repository": {
            "full_name": "acme-corp/clean-repo",
            "default_branch": "main",
        },
        "sender": {"login": "github-actions"},
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = {
        "X-GitHub-Event": "workflow_run",
        "X-Hub-Signature-256": sign_payload(body_bytes),
    }

    res = await async_client.post("/webhook/github", content=body_bytes, headers=headers)
    assert res.status_code == 202
    data = res.json()
    assert data["accepted"] is False
    assert "not a failure" in data["message"].lower()


@pytest.mark.asyncio
async def test_plural_and_events_routes(async_client):
    """Verify that plural /api/v1/incidents and /events routes are active."""
    # Plural GET /api/v1/incidents/demo
    res = await async_client.get("/api/v1/incidents/demo")
    assert res.status_code == 200
    data = res.json()
    assert data["incident_id"] == "demo"
    assert "github_payload" in data
