from __future__ import annotations

import re


def create_recovery_branch_name(
    incident_id: str,
    retry_count: int,
) -> str:
    safe_incident_id = re.sub(
        r"[^a-zA-Z0-9_-]",
        "-",
        incident_id,
    ).strip("-")

    if not safe_incident_id:
        safe_incident_id = "unknown"

    safe_incident_id = safe_incident_id[:60]

    return (
        f"recovery/incident-{safe_incident_id}"
        f"-retry-{retry_count}"
    )
