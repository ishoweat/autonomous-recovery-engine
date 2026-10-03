import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.services.session_service import session_service
from backend.services.incidents import create_incident, list_incidents, get_incident
from backend.db.session import AsyncSessionLocal
from backend.db.models import IncidentStatus

@pytest.mark.asyncio
async def test_multi_user_session_and_incident_isolation():
    # 1. Setup two distinct user sessions
    user_a = {
        "id": 1001,
        "login": "octocat-user-a",
        "name": "User Alpha",
        "avatar_url": "https://avatars.githubusercontent.com/u/1001"
    }
    user_b = {
        "id": 1002,
        "login": "dev-user-b",
        "name": "User Beta",
        "avatar_url": "https://avatars.githubusercontent.com/u/1002"
    }
    
    sess_a_data = await session_service.create_session(user_a, access_token="gho_user_a_token_secret_123")
    sess_b_data = await session_service.create_session(user_b, access_token="gho_user_b_token_secret_456")
    
    token_a = sess_a_data["session_id"]
    token_b = sess_b_data["session_id"]
    
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    
    # 2. Verify session retrieval returns only own identity
    sess_a = await session_service.get_session(token_a)
    sess_b = await session_service.get_session(token_b)
    assert sess_a["username"] == "octocat-user-a"
    assert sess_b["username"] == "dev-user-b"
    assert sess_a["access_token"] != sess_b["access_token"]
    
    # 3. Create incident for User A with unique IDs
    inc_a_id = f"inc_iso_a_{uuid.uuid4().hex[:8]}"
    inc_b_id = f"inc_iso_b_{uuid.uuid4().hex[:8]}"
    repo_a = f"octocat-user-a/repo-{uuid.uuid4().hex[:6]}"
    repo_b = f"dev-user-b/repo-{uuid.uuid4().hex[:6]}"

    async with AsyncSessionLocal() as db:
        incident_a = await create_incident(
            session=db,
            incident_id=inc_a_id,
            github_payload={"action": "completed", "workflow_run": {"id": 99001}},
            repository=repo_a,
            branch="main",
            commit_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            is_mock_mode=False,
            repository_owner="octocat-user-a",
            repository_name=repo_a.split("/")[1],
            repository_full_name=repo_a,
        )
        
        # Create incident for User B
        incident_b = await create_incident(
            session=db,
            incident_id=inc_b_id,
            github_payload={"action": "completed", "workflow_run": {"id": 99002}},
            repository=repo_b,
            branch="feature-x",
            commit_sha="b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3",
            is_mock_mode=False,
            repository_owner="dev-user-b",
            repository_name=repo_b.split("/")[1],
            repository_full_name=repo_b,
        )
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 4. Test User A listing incidents filtered by their repo
        resp_a = await client.get(f"/api/v1/incidents?repository={repo_a}", headers=headers_a)
        assert resp_a.status_code == 200
        data_a = resp_a.json()
        assert len(data_a) == 1
        assert data_a[0]["incident_id"] == inc_a_id
        assert data_a[0]["repository"] == repo_a
        
        # 5. Test User B listing incidents filtered by their repo
        resp_b = await client.get(f"/api/v1/incidents?repository={repo_b}", headers=headers_b)
        assert resp_b.status_code == 200
        data_b = resp_b.json()
        assert len(data_b) == 1
        assert data_b[0]["incident_id"] == inc_b_id
        assert data_b[0]["repository"] == repo_b

        # 6. Auth verification - User A accessing /api/v1/auth/me gets User A
        me_a = await client.get("/api/v1/auth/me", headers=headers_a)
        assert me_a.status_code == 200
        assert me_a.json()["authenticated"] is True
        assert me_a.json()["session"]["username"] == "octocat-user-a"
        
        # User B accessing /api/v1/auth/me gets User B
        me_b = await client.get("/api/v1/auth/me", headers=headers_b)
        assert me_b.status_code == 200
        assert me_b.json()["authenticated"] is True
        assert me_b.json()["session"]["username"] == "dev-user-b"
        
        # Unauthenticated request returns unauthenticated
        me_unauth = await client.get("/api/v1/auth/me")
        assert me_unauth.status_code == 200
        assert me_unauth.json()["authenticated"] is False
