from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.recovery_ext.events import emit_event
from backend.recovery_ext.flags import ExtFlags, get_flags


@pytest.fixture
def mock_flags_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_PERSISTENCE", "false")
    get_flags.cache_clear()
    yield
    get_flags.cache_clear()


@pytest.fixture
def mock_flags_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_PERSISTENCE", "true")
    get_flags.cache_clear()
    yield
    get_flags.cache_clear()


@pytest_asyncio.fixture
async def async_client():
    from backend.recovery_ext.db import init_ext_db
    await init_ext_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_persistence_flag_disabled(mock_flags_disabled, async_client):
    """When ENABLE_PERSISTENCE is false, endpoint returns empty items with persistence_enabled=False."""
    response = await async_client.get("/api/incidents")
    assert response.status_code == 200
    data = response.json()
    assert data["persistence_enabled"] is False
    assert data["items"] == []


@pytest.mark.asyncio
async def test_persistence_flag_enabled(mock_flags_enabled, async_client):
    """When ENABLE_PERSISTENCE is true, emit_event creates records retrievable via API."""
    test_inc_id = "inc_test_phase1_12345"
    await emit_event(
        incident_id=test_inc_id,
        node="TRIAGE",
        type="triage_started",
        payload={"message": "Phase 1 test triage", "repo": "test/repo-1"},
    )
    # Allow background persistence task to finish
    import asyncio
    await asyncio.sleep(0.5)

    res_runs = await async_client.get("/api/incidents")
    assert res_runs.status_code == 200
    data_runs = res_runs.json()
    assert data_runs["persistence_enabled"] is True
    found_run = any(r["incident_id"] == test_inc_id for r in data_runs["items"])
    assert found_run is True

    res_evts = await async_client.get(f"/api/incidents/{test_inc_id}/events")
    assert res_evts.status_code == 200
    data_evts = res_evts.json()
    assert data_evts["persistence_enabled"] is True
    assert data_evts["count"] >= 1
    assert data_evts["events"][0]["node"] == "TRIAGE"
    assert data_evts["events"][0]["type"] == "triage_started"


@pytest.mark.asyncio
async def test_db_failure_does_not_break_pipeline(mock_flags_enabled, monkeypatch):
    """When DB operations fail, emit_event gracefully handles the error without crashing."""
    from backend.recovery_ext.events import _persist_event_to_db
    from backend.services.telemetry import telemetry_manager

    # Mock DB failure
    async def mock_persist(*args, **kwargs):
        raise RuntimeError("Mock DB failure")
    
    monkeypatch.setattr("backend.recovery_ext.events._persist_event_to_db", mock_persist)

    # emit_event should not raise an exception
    await emit_event(
        incident_id="inc_test_failure",
        node="TRIAGE",
        type="triage_started",
        payload={"message": "Phase 1 test failure"},
    )
    # The pipeline survives!
    assert True
