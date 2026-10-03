import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
import hmac
import hashlib
import json
import os

from backend.recovery_ext.models import WebhookDeliveryModel
from backend.db.session import AsyncSessionLocal
from sqlalchemy import select

import httpx

@pytest_asyncio.fixture
async def test_client(monkeypatch):
    monkeypatch.setenv("ENABLE_WEBHOOK_INGRESS", "true")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-secret")
    from backend.recovery_ext.flags import get_flags
    from backend.config import get_settings
    get_flags.cache_clear()
    get_settings.cache_clear()
    
    from backend.main import create_app
    app = create_app()
    
    # We must explicitly call init_ext_db because lifespan is bypassed by httpx.AsyncClient by default,
    # or we can use ASGITransport with lifespan
    from httpx import ASGITransport
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # initialize DB manually because of how AsyncClient works with lifespans
        from backend.db.session import engine
        from backend.recovery_ext.models import ExtBase
        async with engine.begin() as conn:
            await conn.run_sync(ExtBase.metadata.create_all)
            
        yield client

def generate_signature(secret: str, payload_bytes: bytes) -> str:
    return "sha256=" + hmac.new(
        secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()

@pytest.mark.asyncio
async def test_webhook_bad_signature(test_client):
    payload = {"action": "completed", "workflow_run": {"conclusion": "failure"}}
    body = json.dumps(payload).encode("utf-8")
    
    # Bad signature
    headers = {
        "X-Hub-Signature-256": "sha256=invalid123",
        "X-GitHub-Event": "workflow_run",
        "X-GitHub-Delivery": "test-del-1"
    }
    resp = await test_client.post("/api/webhooks/github", content=body, headers=headers)
    assert resp.status_code == 401
    assert "Invalid signature" in resp.json()["detail"]
    
@pytest.mark.asyncio
async def test_webhook_ignored_events(test_client):
    secret = "test-secret"
    
    # Not workflow_run
    payload = {"action": "completed"}
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "X-Hub-Signature-256": generate_signature(secret, body),
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": "test-del-2"
    }
    resp = await test_client.post("/api/webhooks/github", content=body, headers=headers)
    assert resp.status_code == 202
    assert "Ignored event type" in resp.json()["reason"]
    
    # Not failure conclusion
    payload2 = {"action": "completed", "workflow_run": {"conclusion": "success"}}
    body2 = json.dumps(payload2).encode("utf-8")
    headers2 = {
        "X-Hub-Signature-256": generate_signature(secret, body2),
        "X-GitHub-Event": "workflow_run",
        "X-GitHub-Delivery": "test-del-3"
    }
    resp2 = await test_client.post("/api/webhooks/github", content=body2, headers=headers2)
    assert resp2.status_code == 202
    assert "Ignored conclusion" in resp2.json()["reason"]

@pytest.mark.asyncio
async def test_webhook_success_and_dedup(test_client):
    # This also initializes DB inside the test environment by creating the app
    # Need to wait for app lifespan (init_ext_db) to happen, which TestClient does automatically
    secret = "test-secret"
    payload = {
        "action": "completed",
        "workflow_run": {
            "conclusion": "failure",
            "name": "pytest",
            "head_branch": "main",
            "head_sha": "abcdef123"
        },
        "repository": {
            "name": "repo",
            "owner": {"login": "owner"},
            "full_name": "owner/repo"
        }
    }
    body = json.dumps(payload).encode("utf-8")
    import uuid
    test_id = f"test-del-success-{uuid.uuid4().hex}"
    headers = {
        "X-Hub-Signature-256": generate_signature(secret, body),
        "X-GitHub-Event": "workflow_run",
        "X-GitHub-Delivery": test_id
    }
    
    # First delivery should be accepted
    resp = await test_client.post("/api/webhooks/github", content=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    
    # Second delivery with same ID should be ignored (deduplicated)
    resp_dup = await test_client.post("/api/webhooks/github", content=body, headers=headers)
    assert resp_dup.status_code == 202
    assert "Duplicate" in resp_dup.json()["reason"]
