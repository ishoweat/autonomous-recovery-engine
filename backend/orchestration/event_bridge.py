from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable

from backend.orchestration.state import RecoveryState
from backend.services.telemetry import TelemetryEvent, telemetry_manager


TRACKED_STATE_KEYS: tuple[str, ...] = (
    "triage_context",
    "root_cause_analysis",
    "explainable_risk",
    "test_results",
    "retry_count",
)


@dataclass(slots=True, frozen=True)
class StateMutation:
    """
    Represents a single externally visible RecoveryState mutation.
    """

    key: str
    previous: Any
    current: Any


NodeCallable = Callable[..., Awaitable[RecoveryState]]


class IncidentEventBridge:
    """
    Integration boundary between LangGraph and the SSE telemetry layer.

    LangGraph nodes remain responsible for business logic. This class is
    responsible for exposing node lifecycle and important state mutations
    to subscribers without modifying RecoveryState itself.
    """

    def __init__(self, incident_id: str) -> None:
        if not incident_id:
            raise ValueError("incident_id must not be empty")

        self.incident_id = incident_id

    async def node_started(
        self,
        node_name: str,
        *,
        message: str | None = None,
    ) -> TelemetryEvent:
        return await telemetry_manager.publish(
            incident_id=self.incident_id,
            event_type="node_started",
            node_name=node_name,
            message=message or f"{node_name} started",
        )

    async def reasoning(
        self,
        node_name: str,
        reasoning: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> TelemetryEvent:
        return await telemetry_manager.publish(
            incident_id=self.incident_id,
            event_type="reasoning",
            node_name=node_name,
            message=f"{node_name} reasoning",
            reasoning=reasoning,
            metadata=metadata,
        )

    async def node_completed(
        self,
        node_name: str,
        *,
        message: str | None = None,
        state: RecoveryState | None = None,
    ) -> TelemetryEvent:
        event = await telemetry_manager.publish(
            incident_id=self.incident_id,
            event_type="node_completed",
            node_name=node_name,
            message=message or f"{node_name} completed",
            retry_count=(
                state.get("retry_count")
                if state is not None
                else None
            ),
        )

        if state is not None:
            await self.publish_state_mutations(
                node_name=node_name,
                before=None,
                after=state,
            )

        return event

    async def node_failed(
        self,
        node_name: str,
        error: Exception,
    ) -> TelemetryEvent:
        return await telemetry_manager.publish(
            incident_id=self.incident_id,
            event_type="node_failed",
            node_name=node_name,
            message=f"{node_name} failed: {error}",
            metadata={
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )

    async def publish_risk(
        self,
        risk: dict[str, Any],
        *,
        node_name: str = "policy_risk_gateway",
    ) -> TelemetryEvent:
        score = float(risk.get("score", 1.0))

        return await telemetry_manager.publish(
            incident_id=self.incident_id,
            event_type="risk_evaluated",
            node_name=node_name,
            message=(
                f"Risk evaluated: {score:.4f} "
                f"decision={risk.get('decision', 'BLOCK')}"
            ),
            metadata={"explainable_risk": copy.deepcopy(risk)},
            risk_score=score,
        )

    async def publish_approval_required(
        self,
        *,
        risk: dict[str, Any],
        patch_diff: str,
    ) -> TelemetryEvent:
        return await telemetry_manager.publish(
            incident_id=self.incident_id,
            event_type="approval_required",
            node_name="human_approval_node",
            message="Human approval required before recovery continues",
            metadata={
                "explainable_risk": copy.deepcopy(risk),
                "patch_available": bool(patch_diff),
            },
            risk_score=float(risk.get("score", 0.0)),
        )

    async def publish_approval_received(
        self,
        *,
        approved: bool,
        operator: str | None = None,
        reason: str | None = None,
    ) -> TelemetryEvent:
        return await telemetry_manager.publish(
            incident_id=self.incident_id,
            event_type="approval_received",
            node_name="human_approval_node",
            message=(
                "Recovery approved"
                if approved
                else "Recovery rejected"
            ),
            metadata={
                "approved": approved,
                "operator": operator,
                "reason": reason,
            },
        )

    async def publish_state_mutations(
        self,
        *,
        node_name: str,
        before: RecoveryState | None,
        after: RecoveryState,
    ) -> list[TelemetryEvent]:
        events: list[TelemetryEvent] = []

        for mutation in self.diff_state(
            before=before,
            after=after,
        ):
            event = await telemetry_manager.publish(
                incident_id=self.incident_id,
                event_type="state_mutation",
                node_name=node_name,
                message=f"RecoveryState.{mutation.key} updated",
                metadata={
                    "state_key": mutation.key,
                    "previous": mutation.previous,
                    "current": mutation.current,
                },
                retry_count=(
                    after.get("retry_count")
                    if mutation.key != "retry_count"
                    else int(mutation.current)
                ),
                risk_score=(
                    float(after["explainable_risk"].get("score", 0.0))
                    if mutation.key == "explainable_risk"
                    and isinstance(after.get("explainable_risk"), dict)
                    else None
                ),
            )
            events.append(event)

        return events

    @staticmethod
    def diff_state(
        *,
        before: RecoveryState | None,
        after: RecoveryState,
    ) -> list[StateMutation]:
        mutations: list[StateMutation] = []

        for key in TRACKED_STATE_KEYS:
            current = after.get(key)

            if before is None:
                if current in (None, "", {}, []):
                    continue

                mutations.append(
                    StateMutation(
                        key=key,
                        previous=None,
                        current=copy.deepcopy(current),
                    )
                )
                continue

            previous = before.get(key)

            if previous != current:
                mutations.append(
                    StateMutation(
                        key=key,
                        previous=copy.deepcopy(previous),
                        current=copy.deepcopy(current),
                    )
                )

        return mutations

    async def instrument_node(
        self,
        node_name: str,
        node: NodeCallable,
        state: RecoveryState,
        *args: Any,
        **kwargs: Any,
    ) -> RecoveryState:
        """
        Execute a LangGraph node while automatically publishing:

        started -> state mutations -> completed

        Exceptions are published before being re-raised so LangGraph can
        retain its normal failure semantics.
        """

        await self.node_started(node_name)

        before = copy.deepcopy(state)

        try:
            updated = await node(state, *args, **kwargs)

            if not isinstance(updated, dict):
                raise TypeError(
                    f"LangGraph node {node_name!r} returned "
                    f"{type(updated).__name__}; expected dict"
                )

            merged: RecoveryState = {
                **state,
                **updated,
            }

            await self.publish_state_mutations(
                node_name=node_name,
                before=before,
                after=merged,
            )

            await self.node_completed(
                node_name,
                state=merged,
            )

            return merged

        except Exception as exc:
            await self.node_failed(node_name, exc)
            raise


class LangGraphEventDispatcher:
    """
    Convenience dispatcher used by the graph runtime.

    This is intentionally thin so nodes can call one dependency instead of
    directly coupling business logic to the SSE implementation.
    """

    def __init__(self) -> None:
        self._bridges: dict[str, IncidentEventBridge] = {}
        self._lock = asyncio.Lock()

    async def for_incident(
        self,
        incident_id: str,
    ) -> IncidentEventBridge:
        async with self._lock:
            bridge = self._bridges.get(incident_id)

            if bridge is None:
                bridge = IncidentEventBridge(incident_id)
                self._bridges[incident_id] = bridge

            return bridge

    async def remove_incident(
        self,
        incident_id: str,
    ) -> None:
        async with self._lock:
            self._bridges.pop(incident_id, None)


event_dispatcher = LangGraphEventDispatcher()
