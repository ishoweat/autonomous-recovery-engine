from __future__ import annotations

from typing import Any

from backend.orchestration.state import RecoveryState


def create_initial_recovery_state(
    *,
    incident_id: str,
    github_payload: dict[str, Any],
    is_mock_mode: bool,
    is_shadow_mode: bool = True,
    repository_owner: str = "",
    repository_name: str = "",
    repository_full_name: str = "",
    repository_url: str = "",
    default_branch: str = "main",
    source_branch: str = "",
    commit_sha: str = "",
    user_id: str = "",
    username: str = "",
    session_id: str = "",
    user_oauth_token: str = "",
    fork_repo: str = "",
) -> RecoveryState:
    """
    Create the canonical initial state for a recovery execution.

    All fields are initialized explicitly so downstream LangGraph nodes
    never need to rely on missing dictionary keys.
    """

    if not repository_full_name:
        repository_full_name = github_payload.get("repository", {}).get("full_name", "")
    if not repository_owner and "/" in repository_full_name:
        repository_owner = repository_full_name.split("/")[0]
    if not repository_name and "/" in repository_full_name:
        repository_name = repository_full_name.split("/")[1]

    if not repository_url:
        repository_url = (
            github_payload.get("repository", {}).get("html_url")
            or f"https://github.com/{repository_full_name}" if repository_full_name else ""
        )

    if not commit_sha:
        commit_sha = (
            github_payload.get("head_sha")
            or github_payload.get("workflow_run", {}).get("head_sha")
            or github_payload.get("check_run", {}).get("head_sha")
            or github_payload.get("after")
            or ""
        )

    if not source_branch:
        source_branch = (
            github_payload.get("workflow_run", {}).get("head_branch")
            or github_payload.get("check_run", {}).get("check_suite", {}).get("head_branch")
            or default_branch
        )

    # ── Canonical Failure Context Extraction ──────────────────────────────
    failure_file = (
        github_payload.get("failure_file")
        or github_payload.get("failing_file")
        or github_payload.get("filePath")
        or github_payload.get("file_path")
        or (github_payload.get("affected_files", [""])[0] if isinstance(github_payload.get("affected_files"), list) and github_payload.get("affected_files") else "")
        or ""
    )

    failure_line = int(
        github_payload.get("failure_line")
        or github_payload.get("line_number")
        or 0
    )

    error_message = str(
        github_payload.get("error_message")
        or github_payload.get("errorMessage")
        or github_payload.get("error_log")
        or github_payload.get("error_signature")
        or ""
    )

    stack_trace = str(
        github_payload.get("stack_trace")
        or github_payload.get("stackTrace")
        or github_payload.get("error_log")
        or ""
    )

    from backend.config import get_settings
    runtime_model = get_settings().nebius_model

    return RecoveryState(
        incident_id=incident_id,
        repository_owner=repository_owner,
        repository_name=repository_name,
        repository_full_name=repository_full_name,
        repository_url=repository_url,
        default_branch=default_branch,
        source_branch=source_branch,
        commit_sha=commit_sha,
        runtime_model=runtime_model,
        failure_file=failure_file,
        failure_line=failure_line,
        error_message=error_message,
        stack_trace=stack_trace,
        github_payload=github_payload,
        is_mock_mode=is_mock_mode,
        triage_context="",
        root_cause_analysis={},
        explainable_risk={
            "score": 0.0,
            "breakdown": [],
            "decision": "BLOCK",
        },
        action_decision="BLOCK",
        human_approved=False,
        current_patch_diff="",
        test_results={
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
        },
        retry_count=0,
        pr_url="",
        fork_repo=fork_repo,
        user_id=user_id,
        username=username,
        session_id=session_id,
        user_oauth_token=user_oauth_token,
        similar_past_cases=[],
        learning_confidence_boost=0.0,
        patch_explanation="",
        generated_test_code="",
        is_shadow_mode=is_shadow_mode,
        # ARE — Polyglot Fix Engine
        source_files={},
        polyglot_language="python",
        polyglot_audiences={},
        # ARE — Adversarial Resilience Layer
        adversarial_report={},
        # Phase 5 — BLOCK path
        escalation_issue_url="",
        failure_reason="",
    )

