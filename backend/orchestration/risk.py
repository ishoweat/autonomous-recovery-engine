from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RiskContribution:
    """One explainable contribution to the risk score."""

    factor: str
    contribution: float
    explanation: str

    def as_dict(self) -> dict[str, object]:
        return {
            "factor": self.factor,
            "contribution": round(
                self.contribution,
                4,
            ),
            "explanation": self.explanation,
        }


CRITICAL_FILES = {
    "backend/api/auth.py": 0.35,
    "backend/api/webhooks.py": 0.30,
    "backend/db/models.py": 0.30,
    "backend/config.py": 0.20,
}

SENSITIVE_PATH_PATTERNS = (
    re.compile(r"(^|/)auth([^/]*)\.py$"),
    re.compile(r"(^|/)security([^/]*)\.py$"),
    re.compile(r"(^|/)permissions([^/]*)\.py$"),
    re.compile(r"(^|/)crypto([^/]*)\.py$"),
    re.compile(r"(^|/)\.env(\..*)?$"),
    re.compile(r"(^|/)credentials.*$"),
    re.compile(r"(^|/)secrets.*$"),
    re.compile(r"(^|/).*deployment.*$"),
    re.compile(r"(^|/)\.github/workflows/.*$"),
    re.compile(r"(^|/)(kubernetes|k8s|docker-compose).*$"),
)


def _file_criticality(files: list[str]) -> RiskContribution:
    if not files:
        return RiskContribution(
            factor="file_criticality",
            contribution=0.20,
            explanation=(
                "No changed files were identified; uncertainty "
                "increases risk."
            ),
        )

    maximum = 0.10
    selected = ""

    for file_path in files:
        normalized = file_path.strip()

        from backend.recovery_ext.critical_paths import get_critical_path_score
        
        dynamic_score = get_critical_path_score(normalized)
        if dynamic_score is not None:
            score = dynamic_score
        else:
            score = CRITICAL_FILES.get(
                normalized,
                0.10,
            )

        if score > maximum:
            maximum = score
            selected = normalized

    explanation = (
        f"Highest criticality contribution comes from "
        f"{selected}."
        if selected
        else "Changed files are outside the predefined critical set."
    )

    return RiskContribution(
        factor="file_criticality",
        contribution=maximum,
        explanation=explanation,
    )


def _change_scope(files: list[str]) -> RiskContribution:
    count = len(files)

    if count <= 1:
        score = 0.05
    elif count == 2:
        score = 0.12
    elif count <= 4:
        score = 0.20
    else:
        score = 0.30

    return RiskContribution(
        factor="change_scope",
        contribution=score,
        explanation=(
            f"Proposed patch touches {count} file(s)."
        ),
    )


def _security_sensitivity(
    files: list[str],
) -> RiskContribution:
    matches = [
        file_path
        for file_path in files
        if any(
            pattern.search(file_path)
            for pattern in SENSITIVE_PATH_PATTERNS
        )
    ]

    if matches:
        score = 0.20
        explanation = (
            "Security-sensitive paths are included: "
            + ", ".join(matches)
            + "."
        )
    else:
        score = 0.05
        explanation = (
            "No predefined security-sensitive path was detected."
        )

    return RiskContribution(
        factor="security_sensitivity",
        contribution=score,
        explanation=explanation,
    )


def _diff_complexity(
    patch_diff: str,
) -> RiskContribution:
    if not patch_diff.strip():
        return RiskContribution(
            factor="diff_complexity",
            contribution=0.20,
            explanation=(
                "No patch was supplied, so the proposed change "
                "cannot yet be verified."
            ),
        )

    additions = 0
    deletions = 0

    for line in patch_diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue

        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1

    total_changes = additions + deletions

    if total_changes <= 4:
        score = 0.05
    elif total_changes <= 10:
        score = 0.15
    elif total_changes <= 100:
        score = 0.40
    else:
        score = 0.80

    return RiskContribution(
        factor="diff_complexity",
        contribution=score,
        explanation=(
            f"Patch contains {additions} additions and "
            f"{deletions} deletions."
        ),
    )


def calculate_patch_risk(
    *,
    files: list[str],
    patch_diff: str,
    evidence_confidence: str | None = None,
) -> dict[str, object]:
    """Calculate deterministic explainable patch risk."""

    contributions = [
        _file_criticality(files),
        _change_scope(files),
        _security_sensitivity(files),
        _diff_complexity(patch_diff),
    ]

    if evidence_confidence:
        ev_contrib = 0.05 if evidence_confidence == "high" else (0.15 if evidence_confidence == "medium" else 0.35)
        contributions.append(
            RiskContribution(
                factor="external_evidence",
                contribution=ev_contrib,
                explanation=f"Tavily external research evidence confidence is '{evidence_confidence}'",
            )
        )

    raw_score = sum(
        contribution.contribution
        for contribution in contributions
    )

    score = min(
        1.0,
        max(0.0, raw_score),
    )

    # Deterministic adjustment based on external evidence confidence:
    # confidence none/low -> raise risk and require approval; high -> lower risk
    if evidence_confidence in ("none", "low"):
        score = max(score, 0.45)
    elif evidence_confidence == "high":
        score = max(0.05, score - 0.15)

    import os
    force_score = os.environ.get("FORCE_RISK_SCORE")
    # Only allow override in non-production environments
    if force_score and os.environ.get("ENVIRONMENT", "development").lower() != "production":
        try:
            score = float(force_score)
        except ValueError:
            pass

    if score < 0.30 and evidence_confidence not in ("none", "low"):
        decision = "ALLOW"
    elif score <= 0.70 or evidence_confidence in ("none", "low"):
        decision = "APPROVE"
    else:
        decision = "BLOCK"

    return {
        "score": round(score, 4),
        "breakdown": [
            contribution.as_dict()
            for contribution in contributions
        ],
        "decision": decision,
    }

