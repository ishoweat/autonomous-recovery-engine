from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ActionDecision = Literal["ALLOW", "APPROVE", "BLOCK"]


class GitHubRepositorySchema(BaseModel):
    """Minimal repository information extracted from GitHub."""

    model_config = ConfigDict(extra="allow")

    full_name: str = Field(
        min_length=1,
        max_length=255,
    )

    default_branch: str = Field(
        default="main",
        min_length=1,
        max_length=255,
    )


class GitHubSenderSchema(BaseModel):
    """Minimal GitHub actor information."""

    model_config = ConfigDict(extra="allow")

    login: str | None = None


class GitHubWebhookSchema(BaseModel):
    """
    Normalized GitHub webhook payload.

    The original webhook payload is retained separately as a dictionary
    because GitHub sends event-specific fields.
    """

    model_config = ConfigDict(extra="allow")

    action: str | None = None
    ref: str | None = None
    after: str | None = None
    repository: GitHubRepositorySchema
    sender: GitHubSenderSchema | None = None


class IncidentCreateRequest(BaseModel):
    """Internal request model for creating an incident."""

    github_payload: dict[str, Any] = Field(
        min_length=1,
    )

    is_mock_mode: bool = False


class IncidentResponse(BaseModel):
    """Public incident representation."""

    model_config = ConfigDict(from_attributes=True)

    incident_id: str
    status: str
    repository: str
    repository_owner: str | None = None
    repository_name: str | None = None
    repository_full_name: str | None = None
    repository_url: str | None = None
    default_branch: str | None = None
    source_branch: str | None = None
    branch: str
    commit_sha: str | None

    is_mock_mode: bool
    user_id: str | None = None
    username: str | None = None
    github_payload: dict[str, Any] = Field(default_factory=dict)

    triage_context: str
    root_cause_analysis: dict[str, Any]

    explainable_risk: dict[str, Any]

    action_decision: ActionDecision
    human_approved: bool

    current_patch_diff: str
    test_results: dict[str, Any]

    retry_count: int
    pr_url: str

    patch_explanation: str = ""
    generated_test_code: str = ""
    similar_past_cases: list[dict[str, Any]] = Field(default_factory=list)
    learning_confidence_boost: float = 0.0
    is_shadow_mode: bool = True
    runtime_model: str = ""

    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    
    trigger: str | None = None


class IncidentSummaryResponse(BaseModel):
    """Lightweight representation for dashboard incident lists."""

    incident_id: str
    status: str
    repository: str
    branch: str
    action_decision: ActionDecision
    retry_count: int
    is_mock_mode: bool
    created_at: datetime


class IncidentApprovalRequest(BaseModel):
    """Human approval/rejection submitted by Mission Control."""

    approved: bool

    reviewer: str = Field(
        default="operator",
        min_length=1,
        max_length=255,
    )

    reason: str | None = Field(
        default=None,
        max_length=2000,
    )


class IncidentApprovalResponse(BaseModel):
    """Result of a human approval operation."""

    incident_id: str
    approved: bool
    action_decision: ActionDecision
    status: str
    reviewer: str
    reason: str | None


class RiskBreakdownItem(BaseModel):
    """One explainable risk contribution."""

    factor: str
    contribution: float
    explanation: str


class ExplainableRiskSchema(BaseModel):
    """
    Risk gateway result.

    The score is normalized to [0, 1].
    """

    score: float = Field(
        ge=0.0,
        le=1.0,
    )

    breakdown: list[RiskBreakdownItem]

    decision: ActionDecision


class TestResultsSchema(BaseModel):
    """Sandbox execution result."""

    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int | None = None
    tests_passed: bool | None = None


class RootCauseAnalysisSchema(BaseModel):
    """Structured RCA result returned by the reasoning layer."""

    summary: str

    affected_file: str

    error_type: str

    error_message: str

    root_cause: str

    evidence: list[str]

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    proposed_fix: str
