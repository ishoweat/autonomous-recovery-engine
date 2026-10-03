import pytest
import os
from fastapi.testclient import TestClient
from backend.main import app
from backend.db.session import AsyncSessionLocal
from sqlalchemy import text
from backend.orchestration.risk import calculate_patch_risk

@pytest.fixture
def client():
    return TestClient(app)

@pytest.mark.asyncio
async def test_approval_force_score():
    os.environ["FORCE_RISK_SCORE"] = "0.5"
    os.environ["ENVIRONMENT"] = "development"
    risk = calculate_patch_risk(files=["test.py"], patch_diff="+ test")
    assert risk["score"] == 0.5
    assert risk["decision"] == "APPROVE"
    
    os.environ["FORCE_RISK_SCORE"] = "0.9"
    risk2 = calculate_patch_risk(files=["test.py"], patch_diff="+ test")
    assert risk2["score"] == 0.9
    assert risk2["decision"] == "BLOCK"
    
    del os.environ["FORCE_RISK_SCORE"]

def test_approval_endpoint_disabled(client):
    os.environ["ENABLE_APPROVAL_GATE"] = "false"
    from backend.recovery_ext.flags import get_flags
    get_flags.cache_clear()
    
    response = client.post("/api/incidents/test-incident-123/approval", json={"decision": "approve", "operator": "test"})
    assert response.status_code == 400
    assert "not enabled" in response.json()["detail"].lower() or "disabled" in response.json()["detail"].lower()

@pytest.mark.asyncio
async def test_approval_endpoint_enabled_but_not_found(client):
    os.environ["ENABLE_APPROVAL_GATE"] = "true"
    from backend.recovery_ext.flags import get_flags
    get_flags.cache_clear()
    
    response = client.post("/api/incidents/unknown-id/approval", json={"decision": "approve", "operator": "test"})
    assert response.status_code == 404
