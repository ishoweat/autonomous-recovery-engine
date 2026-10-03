import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.mark.asyncio
async def test_get_weekly_learning_report_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/learning/report")
        assert response.status_code == 200
        data = response.json()

        assert "incidents_fixed" in data
        assert data["incidents_fixed"] >= 0
        assert "average_resolution_time_seconds" in data
        assert "most_common_root_causes" in data
        assert len(data["most_common_root_causes"]) > 0
        assert "estimated_time_saved_minutes" in data
        assert "shadow_mode_active" in data
        assert "report_period" in data
        assert isinstance(data["patterns"], list)


@pytest.mark.asyncio
async def test_explain_failure_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Post to explain failure with custom error
        response = await client.post(
            "/api/v1/incident/demo-test-incident/explain-failure",
            json={
                "error_message": "KeyError: 'user_id' in auth handler",
                "affected_file": "backend/api/auth.py",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["incident_id"] == "demo-test-incident"
        assert data["error_type"] == "KeyError"
        assert "simple_explanation" in data
        assert "analogy" in data
        assert "key_takeaway" in data
        assert len(data["simple_explanation"]) > 20

        # 2. Direct learning explanation endpoint
        res2 = await client.post(
            "/api/v1/learning/explain-failure",
            json={"error_message": "ZeroDivisionError: division by zero", "affected_file": "calculator.py"},
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["error_type"] == "ZeroDivisionError"


@pytest.mark.asyncio
async def test_incident_detail_includes_new_learning_fields():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/incident/demo-check-fields")
        assert response.status_code == 200
        data = response.json()

        assert "patch_explanation" in data
        assert "generated_test_code" in data
        assert "similar_past_cases" in data
        assert "learning_confidence_boost" in data
        assert "is_shadow_mode" in data
        assert isinstance(data["is_shadow_mode"], bool)
        assert isinstance(data["similar_past_cases"], list)
