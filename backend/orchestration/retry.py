from __future__ import annotations

from typing import Any

from backend.orchestration.state import RecoveryState
from backend.orchestration.telemetry import emit_node_event


async def increment_retry_node(
    state: RecoveryState,
) -> dict[str, Any]:
    """Increment the bounded autonomous repair counter."""

    next_retry = state["retry_count"] + 1

    await emit_node_event(
        incident_id=state["incident_id"],
        event_type="reasoning",
        node_name="increment_retry_node",
        message=(
            f"Preparing recovery retry {next_retry}."
        ),
        reasoning=(
            "Previous validation did not pass. The repair loop "
            "will continue only while retry_count remains below 3."
        ),
        metadata={
            "previous_retry_count": state[
                "retry_count"
            ],
            "next_retry_count": next_retry,
        },
        retry_count=next_retry,
    )

    return {
        "retry_count": next_retry,
    }
