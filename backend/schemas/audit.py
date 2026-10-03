from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditEventCreate(BaseModel):
    """Internal model used when recording an operational event."""

    event_type: str = Field(
        min_length=1,
        max_length=64,
    )

    node_name: str | None = Field(
        default=None,
        max_length=128,
    )

    message: str = Field(
        min_length=1,
        max_length=10000,
    )

    reasoning: str | None = None

    event_metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    risk_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    retry_count: int | None = Field(
        default=None,
        ge=0,
    )


class AuditEventResponse(BaseModel):
    """Serialized event delivered to clients."""

    model_config = {
        "from_attributes": True,
    }

    id: str
    incident_id: str
    event_type: str
    node_name: str | None

    message: str
    reasoning: str | None

    event_metadata: dict[str, Any]

    risk_score: float | None
    retry_count: int | None

    created_at: datetime


class TelemetryEvent(BaseModel):
    """
    Event contract for the real-time Mission Control stream.

    Phase 2 serialized event model with stable event_id, stage, status, and data.
    """

    event_id: str
    incident_id: str

    event_type: str
    stage: str = "general"
    status: str = "running"

    node_name: str | None = None

    message: str

    reasoning: str | None = None

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
    )

    timestamp: datetime

    risk_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    retry_count: int | None = Field(
        default=None,
        ge=0,
    )

