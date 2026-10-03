from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any


class GitHubWebhookError(ValueError):
    """Raised when a GitHub webhook cannot be trusted or parsed."""


@dataclass(frozen=True, slots=True)
class ParsedGitHubWebhook:
    event_name: str
    action: str | None
    repository: str
    branch: str
    commit_sha: str | None
    sender: str | None
    payload: dict[str, Any]
    is_failure_event: bool
    affected_files: tuple[str, ...]
    github_run_id: str | None = None
    workflow_name: str | None = None
    run_status: str | None = None
    conclusion: str | None = None


def verify_github_signature(
    *,
    payload: bytes,
    signature_header: str | None,
    secret: str,
) -> bool:
    """Verify GitHub's HMAC-SHA256 webhook signature."""

    if not secret or not signature_header:
        return False

    prefix = "sha256="

    if not signature_header.startswith(prefix):
        return False

    supplied_digest = signature_header[len(prefix) :]

    if len(supplied_digest) != 64:
        return False

    expected_digest = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        supplied_digest.lower(),
        expected_digest.lower(),
    )


def _extract_branch(payload: dict[str, Any]) -> str:
    workflow_run = payload.get("workflow_run")
    if isinstance(workflow_run, dict):
        head_branch = workflow_run.get("head_branch")
        if isinstance(head_branch, str) and head_branch:
            return head_branch

    ref = payload.get("ref")

    if isinstance(ref, str) and ref:
        prefix = "refs/heads/"

        if ref.startswith(prefix):
            return ref[len(prefix) :]

        return ref

    repository = payload.get("repository")

    if isinstance(repository, dict):
        default_branch = repository.get("default_branch")

        if isinstance(default_branch, str) and default_branch:
            return default_branch

    return "main"


def _extract_repository(payload: dict[str, Any]) -> str:
    repository = payload.get("repository")

    if not isinstance(repository, dict):
        raise GitHubWebhookError(
            "GitHub webhook is missing repository."
        )

    full_name = repository.get("full_name")

    if not isinstance(full_name, str) or not full_name.strip():
        raise GitHubWebhookError(
            "GitHub webhook is missing repository.full_name."
        )

    return full_name.strip()


def _extract_sender(payload: dict[str, Any]) -> str | None:
    sender = payload.get("sender")

    if not isinstance(sender, dict):
        return None

    login = sender.get("login")

    if isinstance(login, str) and login:
        return login

    return None


def _extract_affected_files(payload: dict[str, Any]) -> tuple[str, ...]:
    paths: set[str] = set()

    commits = payload.get("commits")

    if isinstance(commits, list):
        for commit in commits:
            if not isinstance(commit, dict):
                continue

            for field_name in ("added", "modified", "removed"):
                values = commit.get(field_name)

                if isinstance(values, list):
                    for value in values:
                        if isinstance(value, str) and value:
                            paths.add(value)

    return tuple(sorted(paths))


def _is_failure_event(
    *,
    event_name: str,
    payload: dict[str, Any],
) -> bool:
    if event_name in {"workflow_run", "check_run"}:
        workflow_run = payload.get("workflow_run")
        conclusion = None
        if isinstance(workflow_run, dict):
            conclusion = workflow_run.get("conclusion")
        if not conclusion:
            conclusion = payload.get("conclusion")

        return isinstance(conclusion, str) and conclusion.lower() in {
            "failure",
            "timed_out",
            "action_required",
            "cancelled",
        }

    if event_name == "push":
        commits = payload.get("commits")

        return isinstance(commits, list) and len(commits) > 0

    return event_name == "pull_request"


def parse_github_webhook(
    *,
    event_name: str,
    payload: dict[str, Any],
) -> ParsedGitHubWebhook:
    if not event_name.strip():
        raise GitHubWebhookError(
            "GitHub event name is required."
        )

    repository = _extract_repository(payload)

    branch = _extract_branch(payload)

    workflow_run = payload.get("workflow_run")
    commit_sha = None
    github_run_id = None
    workflow_name = None
    run_status = None
    conclusion = None

    if isinstance(workflow_run, dict):
        head_sha = workflow_run.get("head_sha")
        if isinstance(head_sha, str) and head_sha:
            commit_sha = head_sha
        run_id = workflow_run.get("id")
        if run_id is not None:
            github_run_id = str(run_id)
        name = workflow_run.get("name")
        if isinstance(name, str) and name:
            workflow_name = name
        st = workflow_run.get("status")
        if isinstance(st, str) and st:
            run_status = st
        conc = workflow_run.get("conclusion")
        if isinstance(conc, str) and conc:
            conclusion = conc

    if not commit_sha:
        after = payload.get("after")
        if isinstance(after, str) and after:
            commit_sha = after
        else:
            head_commit = payload.get("head_commit")
            if isinstance(head_commit, dict):
                hc_id = head_commit.get("id")
                if isinstance(hc_id, str) and hc_id:
                    commit_sha = hc_id

    if not github_run_id and payload.get("id"):
        github_run_id = str(payload.get("id"))

    if not conclusion and payload.get("conclusion"):
        conclusion = str(payload.get("conclusion"))

    action = payload.get("action")

    if not isinstance(action, str):
        action = None

    return ParsedGitHubWebhook(
        event_name=event_name,
        action=action,
        repository=repository,
        branch=branch,
        commit_sha=commit_sha,
        sender=_extract_sender(payload),
        payload=payload,
        is_failure_event=_is_failure_event(
            event_name=event_name,
            payload=payload,
        ),
        affected_files=_extract_affected_files(payload),
        github_run_id=github_run_id,
        workflow_name=workflow_name,
        run_status=run_status,
        conclusion=conclusion,
    )
