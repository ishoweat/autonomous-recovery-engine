from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from backend.schemas.audit import TelemetryEvent


class TelemetrySubscription:
    """One live SSE subscription."""

    def __init__(
        self,
        *,
        incident_id: str,
        queue: asyncio.Queue[TelemetryEvent],
        manager: TelemetryManager,
    ) -> None:
        self.incident_id = incident_id
        self.queue = queue
        self._manager = manager
        self._closed = False

    async def get(self) -> TelemetryEvent:
        return await self.queue.get()

    def get_nowait(self) -> TelemetryEvent:
        return self.queue.get_nowait()

    def empty(self) -> bool:
        return self.queue.empty()

    async def close(self) -> None:
        if self._closed:
            return

        self._closed = True

        await self._manager.unsubscribe(
            incident_id=self.incident_id,
            queue=self.queue,
        )

    async def __aenter__(self) -> TelemetrySubscription:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        await self.close()


class TelemetryManager:
    """
    In-process telemetry fan-out.

    Durable history is stored in PostgreSQL. asyncio.Queue provides the
    real-time path used by SSE clients.
    """

    def __init__(self, queue_size: int = 100, max_history: int = 200) -> None:
        if queue_size < 1:
            raise ValueError(
                "queue_size must be greater than zero."
            )

        self._queue_size = queue_size
        self._max_history = max_history

        self._subscribers: dict[
            str,
            set[asyncio.Queue[TelemetryEvent]],
        ] = defaultdict(set)
        self._history: dict[str, list[TelemetryEvent]] = defaultdict(list)

        self._lock = asyncio.Lock()

    async def subscribe(
        self,
        incident_id: str,
        replay_history: bool = True,
    ) -> TelemetrySubscription:
        queue: asyncio.Queue[TelemetryEvent] = asyncio.Queue(
            maxsize=self._queue_size,
        )

        async with self._lock:
            self._subscribers[incident_id].add(queue)
            history_events = self._history.get(incident_id)
            if (not history_events or len(history_events) == 0) and replay_history:
                db_events = await self._load_history_from_db(incident_id)
                if db_events:
                    self._history[incident_id] = db_events
                    history_events = db_events

            if replay_history and history_events:
                for past_event in history_events:
                    self._put_latest(
                        queue=queue,
                        event=past_event,
                    )

        return TelemetrySubscription(
            incident_id=incident_id,
            queue=queue,
            manager=self,
        )

    async def unsubscribe(
        self,
        *,
        incident_id: str,
        queue: asyncio.Queue[TelemetryEvent],
    ) -> None:
        async with self._lock:
            subscribers = self._subscribers.get(incident_id)

            if subscribers is None:
                return

            subscribers.discard(queue)

            if not subscribers:
                del self._subscribers[incident_id]

    async def publish(
        self,
        *,
        incident_id: str,
        event_type: str,
        message: str = "",
        stage: str | None = None,
        status: str | None = None,
        node_name: str | None = None,
        reasoning: str | None = None,
        metadata: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        risk_score: float | None = None,
        retry_count: int | None = None,
    ) -> TelemetryEvent:
        def _sanitize_val(val: Any) -> Any:
            if val is Ellipsis:
                return None
            if isinstance(val, dict):
                return {str(k): _sanitize_val(v) for k, v in val.items()}
            if isinstance(val, (list, tuple, set)):
                return [_sanitize_val(v) for v in val]
            return val

        combined_data = _sanitize_val({**(metadata or {}), **(data or {})})

        # Infer stage if not explicitly given
        inferred_stage = stage
        if not inferred_stage:
            node_lower = (node_name or "").lower()
            event_lower = event_type.lower()
            if "triage" in node_lower or "detect" in event_lower:
                inferred_stage = "triage"
            elif "nemotron" in event_lower or "root_cause" in node_lower or "root_cause" in event_lower:
                inferred_stage = "root_cause"
            elif "patch" in event_lower or "repair" in node_lower:
                inferred_stage = "repair"
            elif "sandbox" in node_lower or "sandbox" in event_lower or "failure_analyzer" in node_lower:
                inferred_stage = "sandbox"
            elif "adversarial" in node_lower or "mutation" in event_lower or "dependency" in event_lower or "behavioral" in event_lower:
                inferred_stage = "adversarial"
            elif "risk" in node_lower or "risk" in event_lower:
                inferred_stage = "risk"
            elif "approval" in node_lower or "approval" in event_lower or event_lower == "approved":
                inferred_stage = "approval"
            elif "pr" in event_lower or "branch" in event_lower or "commit" in event_lower or "recover" in node_lower or "recover" in event_lower:
                inferred_stage = "recovery"
            elif event_lower in {"webhook", "incident_created"}:
                inferred_stage = "triage"
            else:
                inferred_stage = "general"

        # Infer status if not explicitly given
        inferred_status = status
        if not inferred_status:
            event_lower = event_type.lower()
            if event_lower.endswith("_completed") or event_lower in {
                "incident_recovered", "patch_generated", "root_cause_identified",
                "pr_created", "pr_reused", "approval_granted", "approved", "source_loaded", "branch_created",
                "commit_created", "adversarial_validation_completed", "risk_evaluated",
                "test_completed", "triage", "root_cause", "incident_created"
            }:
                inferred_status = "completed"
            elif event_lower.endswith("_failed") or event_lower in {"escalated", "approval_rejected"}:
                inferred_status = "failed"
            elif event_lower in {"approval_required", "approval_requested"}:
                inferred_status = "waiting_for_human"
            else:
                inferred_status = "running"

        event = TelemetryEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            incident_id=incident_id,
            event_type=event_type,
            stage=inferred_stage,
            status=inferred_status,
            node_name=node_name,
            message=message,
            reasoning=reasoning,
            metadata=combined_data,
            data=combined_data,
            timestamp=datetime.now(timezone.utc),
            risk_score=risk_score,
            retry_count=retry_count,
        )

        async with self._lock:
            history = self._history[incident_id]
            history.append(event)
            if len(history) > self._max_history:
                self._history[incident_id] = history[-self._max_history:]

            subscribers = tuple(
                self._subscribers.get(
                    incident_id,
                    set(),
                )
            )

        for queue in subscribers:
            self._put_latest(
                queue=queue,
                event=event,
            )

        # Asynchronously persist audit event into database
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._persist_to_db(incident_id, event))
            from backend.recovery_ext.flags import get_flags
            if get_flags().enable_persistence:
                from backend.recovery_ext.events import _persist_event_to_db
                loop.create_task(_persist_event_to_db(incident_id, node_name or "general", event_type, combined_data))
        except RuntimeError:
            pass

        return event

    async def get_history(self, incident_id: str) -> list[TelemetryEvent]:
        async with self._lock:
            events = list(self._history.get(incident_id, []))
            if not events:
                db_events = await self._load_history_from_db(incident_id)
                if db_events:
                    self._history[incident_id] = db_events
                    return list(db_events)
            return events

    async def _persist_to_db(self, incident_id: str, event: TelemetryEvent) -> None:
        try:
            from backend.db.session import AsyncSessionLocal
            from backend.db.models import Incident, AuditTrail, AuditEventType
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    select(Incident.id).where(Incident.incident_id == incident_id)
                )
                inc_uuid = res.scalar_one_or_none()
                if inc_uuid:
                    try:
                        enum_type = AuditEventType(event.event_type)
                    except ValueError:
                        enum_type = AuditEventType.NODE_STARTED

                    audit = AuditTrail(
                        incident_id=inc_uuid,
                        event_type=enum_type,
                        node_name=event.node_name,
                        message=event.message,
                        reasoning=event.reasoning,
                        event_metadata=event.metadata,
                        risk_score=event.risk_score,
                        retry_count=event.retry_count,
                    )
                    session.add(audit)
                    await session.commit()
        except Exception:
            pass

    async def _load_history_from_db(self, incident_id: str) -> list[TelemetryEvent]:
        try:
            from backend.db.session import AsyncSessionLocal
            from backend.db.models import Incident, AuditTrail
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    select(AuditTrail)
                    .join(Incident, AuditTrail.incident_id == Incident.id)
                    .where(Incident.incident_id == incident_id)
                    .order_by(AuditTrail.created_at.asc())
                )
                rows = res.scalars().all()
                events: list[TelemetryEvent] = []
                for row in rows:
                    events.append(
                        TelemetryEvent(
                            event_id=f"evt_{row.id.hex[:12]}",
                            incident_id=incident_id,
                            event_type=str(row.event_type),
                            node_name=row.node_name,
                            message=row.message,
                            reasoning=row.reasoning,
                            metadata=row.event_metadata or {},
                            data=row.event_metadata or {},
                            timestamp=row.created_at,
                            risk_score=row.risk_score,
                            retry_count=row.retry_count,
                        )
                    )
                return events
        except Exception:
            return []

    @staticmethod
    def _put_latest(
        *,
        queue: asyncio.Queue[TelemetryEvent],
        event: TelemetryEvent,
    ) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            TelemetryManager._discard_oldest(queue)

            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                return

    @staticmethod
    def _discard_oldest(
        queue: asyncio.Queue[TelemetryEvent],
    ) -> None:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            return


telemetry_manager = TelemetryManager()
