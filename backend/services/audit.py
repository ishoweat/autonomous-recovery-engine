from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AuditEventType, AuditTrail
from backend.schemas.audit import AuditEventCreate
from backend.services.telemetry import telemetry_manager


async def record_audit_event(
    *,
    session: AsyncSession,
    incident_uuid: uuid.UUID,
    incident_id: str,
    event: AuditEventCreate,
) -> AuditTrail:
    """Persist an audit event and broadcast it to live SSE clients."""

    audit = AuditTrail(
        incident_id=incident_uuid,
        event_type=AuditEventType(event.event_type),
        node_name=event.node_name,
        message=event.message,
        reasoning=event.reasoning,
        event_metadata=event.event_metadata,
        risk_score=event.risk_score,
        retry_count=event.retry_count,
    )

    session.add(audit)

    await session.flush()

    await telemetry_manager.publish(
        incident_id=incident_id,
        event_type=event.event_type,
        node_name=event.node_name,
        message=event.message,
        reasoning=event.reasoning,
        metadata=event.event_metadata,
        risk_score=event.risk_score,
        retry_count=event.retry_count,
    )

    return audit
