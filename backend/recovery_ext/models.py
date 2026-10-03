from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, DateTime, Float, Index, JSON, String, Text
from sqlalchemy.orm import declarative_base

ExtBase = declarative_base()


class IncidentRunModel(ExtBase):
    """Stores durable incident run executions."""

    __tablename__ = "incident_runs"

    id = Column(String(64), primary_key=True, default=lambda: f"run_{uuid.uuid4().hex[:12]}")
    incident_id = Column(String(128), nullable=False, index=True)
    repo = Column(String(256), nullable=True, default="")
    status = Column(String(64), nullable=False, default="running")
    risk_score = Column(Float, nullable=True, default=0.0)
    decision = Column(String(64), nullable=True, default="PENDING")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class IncidentEventModel(ExtBase):
    """Stores durable incident telemetry and workflow events."""

    __tablename__ = "incident_events"

    id = Column(String(64), primary_key=True, default=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    incident_id = Column(String(128), nullable=False, index=True)
    node = Column(String(128), nullable=True, default="general")
    type = Column(String(128), nullable=False, default="info")
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class ApprovalModel(ExtBase):
    """Stores human approval decisions for incident runs."""

    __tablename__ = "approvals"

    id = Column(String(64), primary_key=True, default=lambda: f"appr_{uuid.uuid4().hex[:12]}")
    incident_id = Column(String(128), nullable=False, index=True)
    state = Column(String(64), nullable=False, default="PENDING")
    decided_by = Column(String(128), nullable=True, default="operator")
    decided_at = Column(DateTime(timezone=True), nullable=True)


class WebhookDeliveryModel(ExtBase):
    """Stores processed webhook delivery IDs for deduplication."""

    __tablename__ = "webhook_deliveries"

    delivery_id = Column(String(128), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


Index("idx_incident_runs_inc_id", IncidentRunModel.incident_id)
Index("idx_incident_events_inc_id", IncidentEventModel.incident_id)
Index("idx_approvals_inc_id", ApprovalModel.incident_id)
