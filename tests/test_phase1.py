import asyncio
import pytest
from datetime import datetime
import uuid

from backend.db.models import Incident, AuditTrail, IncidentStatus, AuditEventType
from backend.schemas.incident import IncidentCreateRequest, IncidentResponse, ExplainableRiskSchema
from backend.schemas.audit import AuditEventCreate, TelemetryEvent
from backend.orchestration.state import RecoveryState
from backend.orchestration.state_factory import create_initial_recovery_state


def test_recovery_state_factory():
    state = create_initial_recovery_state(
        incident_id="inc-test-001",
        github_payload={"repository": {"full_name": "owner/repo"}},
        is_mock_mode=True,
    )
    assert state["incident_id"] == "inc-test-001"
    assert state["is_mock_mode"] is True
    assert state["action_decision"] == "BLOCK"
    assert state["retry_count"] == 0
    assert state["current_patch_diff"] == ""


def test_schema_validations():
    req = IncidentCreateRequest(
        github_payload={"action": "completed", "repository": {"full_name": "test/repo"}},
        is_mock_mode=False
    )
    assert req.is_mock_mode is False
    assert req.github_payload["action"] == "completed"

    risk = ExplainableRiskSchema(
        score=0.45,
        breakdown=[{"factor": "auth_change", "contribution": 0.45, "explanation": "Modifies auth module"}],
        decision="APPROVE"
    )
    assert risk.score == 0.45
    assert risk.decision == "APPROVE"


def test_orm_models_instantiation():
    inc = Incident(
        incident_id="inc-123",
        status=IncidentStatus.RECEIVED,
        repository="org/repo",
        branch="main",
        commit_sha="abc1234",
        is_mock_mode=False,
        github_payload={"event": "workflow_job"},
    )
    assert inc.incident_id == "inc-123"
    assert inc.status == IncidentStatus.RECEIVED

    audit = AuditTrail(
        incident_id=inc.id,
        event_type=AuditEventType.INCIDENT_CREATED,
        message="Incident inc-123 created",
    )
    assert audit.event_type == AuditEventType.INCIDENT_CREATED
