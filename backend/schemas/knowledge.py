from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KnowledgePatternCreate(BaseModel):
    """Payload for creating a new learned pattern in the knowledge base."""

    incident_id: str | None = None
    repository: str = ""
    error_type: str = Field(..., min_length=1, max_length=128)
    root_cause_summary: str = Field(..., min_length=1)
    patch_pattern: str = Field(..., min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    file_path: str | None = None
    pattern_metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgePatternResponse(BaseModel):
    """Representation of a learned pattern returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: str | None
    repository: str
    error_type: str
    root_cause_summary: str
    patch_pattern: str
    confidence: float
    file_path: str | None
    pattern_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class KnowledgePatternMatchResponse(BaseModel):
    """Result of querying the knowledge base for similar incident patterns."""

    matched: bool
    confidence_boost: float = 0.0
    best_pattern: KnowledgePatternResponse | None = None
    matches: list[KnowledgePatternResponse] = Field(default_factory=list)


class RootCauseFrequency(BaseModel):
    """Frequency distribution of root causes for reporting."""

    root_cause: str
    error_type: str
    count: int
    percentage: float


class WeeklyLearningReportResponse(BaseModel):
    """Weekly learning metrics aggregating incidents fixed, speed, patterns and time saved."""

    incidents_fixed: int
    average_resolution_time_seconds: float
    most_common_root_causes: list[RootCauseFrequency]
    estimated_time_saved_minutes: float
    total_learned_patterns: int
    shadow_mode_active: bool
    report_period: str = "Last 7 Days"
    patterns: list[KnowledgePatternResponse] = Field(default_factory=list)


class ExplainFailureRequest(BaseModel):
    """Optional payload for requesting an error explanation."""

    error_message: str | None = None
    code_context: str | None = None
    affected_file: str | None = None


class ExplainFailureResponse(BaseModel):
    """Human-friendly plain English explanation of a failure."""

    incident_id: str
    error_type: str
    simple_explanation: str
    analogy: str
    key_takeaway: str
    affected_file: str | None = None

