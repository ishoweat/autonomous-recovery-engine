from dataclasses import dataclass
from typing import Any, TypedDict


@dataclass(frozen=True, slots=True)
class CanonicalRecoveryContext:
    """
    Immutable canonical recovery context bound to a single incident.
    Ensures failure_file, failure_line, commit_sha, error_message, stack_trace,
    and repository_full_name remain bound throughout triage, root-cause, repair,
    sandbox verification, and GitHub PR creation.
    """

    incident_id: str
    repository_full_name: str
    commit_sha: str
    failure_file: str
    failure_line: int = 0
    error_message: str = ""
    stack_trace: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "repository_full_name": self.repository_full_name,
            "commit_sha": self.commit_sha,
            "failure_file": self.failure_file,
            "failure_line": self.failure_line,
            "error_message": self.error_message,
            "stack_trace": self.stack_trace,
        }


class RecoveryState(TypedDict):
    """
    Canonical state shared by every Autonomous Recovery Engine node.

    This schema is intentionally kept stable because every LangGraph node,
    persistence layer, telemetry event, and frontend state transition
    depends on these fields.
    """

    incident_id: str

    repository_owner: str
    repository_name: str
    repository_full_name: str
    repository_url: str
    default_branch: str
    source_branch: str
    commit_sha: str
    runtime_model: str

    # ── Canonical Failure Context ──────────────────────────────────────────
    failure_file: str
    failure_line: int
    error_message: str
    stack_trace: str

    github_payload: dict

    is_mock_mode: bool

    triage_context: str

    root_cause_analysis: dict

    # Expected shape:
    # {
    #     "score": float,
    #     "breakdown": list,
    #     "decision": str
    # }
    explainable_risk: dict

    # ALLOW  -> score < 0.3
    # APPROVE -> 0.3 <= score <= 0.7
    # BLOCK -> score > 0.7
    action_decision: str

    human_approved: bool

    current_patch_diff: str

    # Expected shape:
    # {
    #     "stdout": str,
    #     "stderr": str,
    #     "exit_code": int
    # }
    test_results: dict

    # Maximum allowed retry count is 3.
    # When retry_count > 3, the graph routes to escalation.
    retry_count: int

    pr_url: str
    fork_repo: str

    # ── Authenticated User & Session Association ──
    user_id: str
    username: str
    session_id: str
    user_oauth_token: str

    # ── Learning, Memory & Shadow Mode extensions ──
    similar_past_cases: list[dict]
    learning_confidence_boost: float
    patch_explanation: str
    generated_test_code: str
    is_shadow_mode: bool

    # ── Polyglot Fix Engine (ARE Option 2) ──────────────────────────────────
    # Raw {filename: content} map of files the repair node may modify.
    # Populated by the caller / API layer before graph execution.
    source_files: dict  # {filename: str}

    # Language detected by PolyglotFixEngine ("python", "go", "rust", …)
    polyglot_language: str

    # {devops, product, researcher} multi-audience explanations
    polyglot_audiences: dict

    # ── Adversarial Resilience Layer (ARE Option 1) ──────────────────────────
    # Expected shape mirrors AdversarialReport.as_dict():
    # {
    #     "mutation_score": float,
    #     "cve_hits": list,
    #     "behavioral_flags": list,
    #     "overall_safe": bool,
    #     "confidence": float,
    #     "summary": str,
    #     "raw": dict
    # }
    adversarial_report: dict

    # ── Phase 5: BLOCK path fields ──────────────────────────────────────────
    # URL of the GitHub issue created by human_escalation (None if not created)
    escalation_issue_url: str
    # Reason for failure: "BLOCKED_BY_POLICY", "APPROVAL_REJECTED", etc.
    failure_reason: str

