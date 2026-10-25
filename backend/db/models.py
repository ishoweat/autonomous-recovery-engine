from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    CHAR,
    func,
)
from sqlalchemy.types import TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base


class GUID(TypeDecorator):
    """Platform-independent GUID type.
    Uses PostgreSQL's UUID type, otherwise uses CHAR(36).
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(uuid.UUID(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(value)
        return value


# Dialect-agnostic type definitions
JSONB_TYPE = JSONB().with_variant(JSON, "sqlite")
UUID_TYPE = GUID()


class IncidentStatus(StrEnum):
    """Lifecycle status of an autonomous recovery incident."""

    RECEIVED = "received"
    TRIAGING = "triaging"
    ANALYZING = "analyzing"
    RISK_REVIEW = "risk_review"
    AWAITING_APPROVAL = "awaiting_approval"
    REPAIRING = "repairing"
    TESTING = "testing"
    ESCALATED = "escalated"
    RECOVERED = "recovered"
    FAILED = "failed"
    PR_OPEN = "pr_open"
    VERIFIED_POST_MERGE = "VERIFIED_POST_MERGE"
    DRIFT_DETECTED = "DRIFT_DETECTED"


class AuditEventType(StrEnum):
    """Categories of events emitted during incident recovery."""

    WEBHOOK = "webhook"
    INCIDENT_CREATED = "incident_created"
    TRIAGE = "triage"
    ROOT_CAUSE = "root_cause"
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    REASONING = "reasoning"
    RISK_EVALUATED = "risk_evaluated"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RECEIVED = "approval_received"
    APPROVED = "approved"
    PATCH_GENERATED = "patch_generated"
    SANDBOX_STARTED = "sandbox_started"
    SANDBOX_COMPLETED = "sandbox_completed"
    TEST_STARTED = "test_started"
    TEST_COMPLETED = "test_completed"
    BRANCH_CREATED = "branch_created"
    COMMIT_CREATED = "commit_created"
    PR_CREATED = "pr_created"
    PR_REUSED = "pr_reused"
    ESCALATED = "escalated"
    INCIDENT_RECOVERED = "incident_recovered"


class Incident(Base):
    """
    Persistent representation of a single GitHub-triggered recovery attempt.

    The mutable operational state is stored explicitly so the application
    can survive process restarts and reconstruct the current mission state.
    """

    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
    )

    incident_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
    )

    status: Mapped[IncidentStatus] = mapped_column(
        String(32),
        nullable=False,
        default=IncidentStatus.RECEIVED,
        index=True,
    )

    repository: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    repository_owner: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="",
    )

    repository_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="",
    )

    repository_full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
    )

    repository_url: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        default="",
    )

    branch: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="main",
    )

    default_branch: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="main",
    )

    source_branch: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
    )

    commit_sha: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    
    workflow_run_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="",
    )

    is_mock_mode: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        index=True,
    )

    is_demo: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        index=True,
    )

    user_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    username: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    session_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    github_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB_TYPE,
        nullable=False,
        default=dict,
    )

    triage_context: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    root_cause_analysis: Mapped[dict[str, Any]] = mapped_column(
        JSONB_TYPE,
        nullable=False,
        default=dict,
    )

    explainable_risk: Mapped[dict[str, Any]] = mapped_column(
        JSONB_TYPE,
        nullable=False,
        default=dict,
    )

    action_decision: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="BLOCK",
    )

    human_approved: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
    )

    current_patch_diff: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    test_results: Mapped[dict[str, Any]] = mapped_column(
        JSONB_TYPE,
        nullable=False,
        default=dict,
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    pr_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    patch_explanation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    generated_test_code: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    similar_past_cases: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB_TYPE,
        nullable=False,
        default=list,
    )

    learning_confidence_boost: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    is_shadow_mode: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    @property
    def trigger(self) -> str | None:
        if isinstance(self.github_payload, dict):
            return self.github_payload.get("workflow_run", {}).get("trigger")
        return None

    audit_events: Mapped[list[AuditTrail]] = relationship(
        "AuditTrail",
        back_populates="incident",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AuditTrail.created_at",
    )

    __table_args__ = (
        Index(
            "ix_incidents_status_created_at",
            "status",
            "created_at",
        ),
        Index(
            "ix_incidents_repository_branch",
            "repository",
            "branch",
        ),
    )


class AuditTrail(Base):
    """
    Persistent event log for incident execution.

    Each row represents an observable event that can later be streamed
    to Mission Control or used for forensic reconstruction.
    """

    __tablename__ = "audit_trails"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey(
            "incidents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    event_type: Mapped[AuditEventType] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    node_name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    reasoning: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB_TYPE,
        nullable=False,
        default=dict,
    )

    risk_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    retry_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    incident: Mapped[Incident] = relationship(
        "Incident",
        back_populates="audit_events",
    )

    __table_args__ = (
        Index(
            "ix_audit_incident_created_at",
            "incident_id",
            "created_at",
        ),
    )


class KnowledgePattern(Base):
    """
    Persistent representation of a learned fix pattern stored in the Knowledge Base.

    Stores successful root causes, error types, patch patterns, and confidence
    scores to accelerate future incident remediation and boost confidence.
    """

    __tablename__ = "knowledge_base"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
    )

    incident_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    repository: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        index=True,
    )

    error_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    root_cause_summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    patch_pattern: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
    )

    file_path: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    pattern_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB_TYPE,
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index(
            "ix_knowledge_error_repo",
            "error_type",
            "repository",
        ),
    )


class FixRecord(Base):
    """
    Economic ROI record for a single successful automated fix.

    Populated by ROITracker.record_fix() at the end of every successful
    recovery_complete_node execution.  Drives the /api/v1/roi/* endpoints.
    """

    __tablename__ = "fix_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
    )

    # Logical identifier — incident_id from RecoveryState
    fix_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
    )

    language: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="python",
        index=True,
    )

    # LOW / MEDIUM / HIGH  (mirrors explainable_risk decision vocabulary)
    severity: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="LOW",
        index=True,
    )

    # Time the failure was open before ARE resolved it (minutes)
    mttr_before_min: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    # Wall-clock time ARE spent on the fix (minutes)
    mttr_after_min: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    # True when the fix required no human approval
    was_automated: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
    )

    is_demo: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        index=True,
    )

    repository: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        index=True,
    )

    # Derived fields (computed at insert time)
    human_hours_saved: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    cost_saved_usd: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    incident_prevented: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_fix_records_repo_created_at",
            "repository",
            "created_at",
        ),
        Index(
            "ix_fix_records_severity_created_at",
            "severity",
            "created_at",
        ),
    )


class SystemAnalytics(Base):
    """System-wide analytics and aggregated counters."""

    __tablename__ = "system_analytics"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    resolutions_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

