from __future__ import annotations

from typing import Any

from backend.services.telemetry import telemetry_manager


async def emit_node_event(
    *,
    incident_id: str,
    event_type: str,
    node_name: str,
    message: str,
    reasoning: str | None = None,
    metadata: dict[str, Any] | None = None,
    risk_score: float | None = None,
    retry_count: int | None = None,
) -> None:
    """Publish an execution event to the Phase 2 SSE manager."""

    await telemetry_manager.publish(
        incident_id=incident_id,
        event_type=event_type,
        node_name=node_name,
        message=message,
        reasoning=reasoning,
        metadata=metadata or {},
        risk_score=risk_score,
        retry_count=retry_count,
    )
