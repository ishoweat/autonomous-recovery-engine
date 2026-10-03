from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from backend.db.session import AsyncSessionLocal
from backend.recovery_ext.flags import get_flags
from backend.recovery_ext.models import IncidentEventModel, IncidentRunModel
from backend.services.telemetry import telemetry_manager

logger = logging.getLogger(__name__)


def _sanitize_payload(obj: Any) -> Any:
    if obj is Ellipsis:
        return None
    if isinstance(obj, dict):
        return {str(k): _sanitize_payload(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_sanitize_payload(v) for v in obj]
    return obj


async def _persist_event_to_db(incident_id: str, node: str, event_type: str, payload: dict[str, Any]) -> None:
    try:
        clean_payload = _sanitize_payload(payload)
        async with AsyncSessionLocal() as session:
            evt = IncidentEventModel(
                incident_id=incident_id,
                node=node or "general",
                type=event_type,
                payload=clean_payload,
                created_at=datetime.now(timezone.utc),
            )
            session.add(evt)

            # Ensure run entry exists
            repo = str(clean_payload.get("repository") or clean_payload.get("repo") or "")
            status = str(clean_payload.get("status") or "running")
            risk_score = clean_payload.get("risk_score")
            try:
                risk_score_float = float(risk_score) if risk_score is not None else None
            except (ValueError, TypeError):
                risk_score_float = None

            from sqlalchemy import select
            res = await session.execute(select(IncidentRunModel).where(IncidentRunModel.incident_id == incident_id))
            existing_run = res.scalars().first()
            if not existing_run:
                run = IncidentRunModel(
                    incident_id=incident_id,
                    repo=repo,
                    status=status,
                    risk_score=risk_score_float,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(run)
            else:
                if status:
                    existing_run.status = status
                if risk_score_float is not None:
                    existing_run.risk_score = risk_score_float
                if repo:
                    existing_run.repo = repo
                existing_run.updated_at = datetime.now(timezone.utc)

            await session.commit()
    except Exception as exc:
        logger.warning(f"[PERSISTENCE WARNING] Failed to persist event for incident {incident_id}: {exc}")


async def emit_event(
    incident_id: str,
    node: str,
    type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """
    Emit event helper for Autonomous Recovery Engine extensions.
    - If ENABLE_PERSISTENCE is True, writes to incident_events DB table without blocking.
    - Forwards event to existing SSE telemetry stream with unchanged shape.
    """
    flags = get_flags()
    clean_payload = _sanitize_payload(payload or {})

    # 1. Non-blocking persistence if enabled
    if flags.enable_persistence:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_persist_event_to_db(incident_id, node, type, clean_payload))
        except RuntimeError:
            pass

    # 2. Forward to existing telemetry SSE manager (unchanged payload shape)
    msg = str(clean_payload.get("message") or clean_payload.get("reasoning") or f"Event {type} in node {node}")
    try:
        await telemetry_manager.publish(
            incident_id=incident_id,
            event_type=type,
            message=msg,
            node_name=node,
            data=clean_payload,
            metadata=clean_payload,
        )
    except Exception as exc:
        logger.warning(f"Failed to forward telemetry event to SSE manager: {exc}")
