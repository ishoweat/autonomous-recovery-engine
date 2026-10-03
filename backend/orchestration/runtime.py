from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from backend.config import get_settings
from backend.llm.nebius import (
    NebiusNemotron,
    create_nebius_client,
)
from backend.orchestration.graph import build_recovery_graph
from backend.orchestration.state import RecoveryState
from backend.services.telemetry import telemetry_manager


def _checkpoint_database_url(
    database_url: str,
) -> str:
    if database_url.startswith(
        "postgresql+asyncpg://"
    ):
        return database_url.replace(
            "postgresql+asyncpg://",
            "postgresql://",
            1,
        )

    return database_url


class RecoveryRuntime:
    """Process-wide LangGraph runtime."""

    def __init__(self) -> None:
        self.checkpointer: BaseCheckpointSaver | None = None
        self.llm: NebiusNemotron | None = None
        self.graph: Any = None
        self._checkpointer_context: Any = None

    async def start(self) -> None:
        settings = get_settings()

        database_url = _checkpoint_database_url(
            settings.database_url
        )

        try:
            checkpointer_context = AsyncPostgresSaver.from_conn_string(database_url)
            self.checkpointer = await checkpointer_context.__aenter__()
            self._checkpointer_context = checkpointer_context

            if settings.langgraph_checkpoint_setup:
                await self.checkpointer.setup()
        except Exception:
            # Fallback to MemorySaver for testing or non-Postgres environments
            self.checkpointer = MemorySaver()

        if settings.nebius_api_key:
            self.llm = create_nebius_client()
            from backend.llm.nebius import create_nebius_fast_client
            self.fast_llm = create_nebius_fast_client()
        else:
            self.fast_llm = None

        self.graph = build_recovery_graph(
            checkpointer=self.checkpointer,
            llm=self.llm,
            fast_llm=self.fast_llm,
        )

    async def stop(self) -> None:
        if self.llm is not None:
            await self.llm.close()

        if self._checkpointer_context is not None:
            try:
                await self._checkpointer_context.__aexit__(None, None, None)
            except Exception:
                pass

        self.graph = None
        self.llm = None
        self.checkpointer = None
        self._checkpointer_context = None

    def _require_graph(self) -> Any:
        if self.graph is None:
            raise RuntimeError(
                "Recovery runtime has not been initialized."
            )

        return self.graph

    async def get_state(self, incident_id: str) -> dict[str, Any] | None:
        """Retrieve current graph state for an incident."""
        graph = self._require_graph()
        config = {"configurable": {"thread_id": incident_id}}
        try:
            state_snapshot = await graph.aget_state(config)
            if state_snapshot and hasattr(state_snapshot, "values") and state_snapshot.values:
                return dict(state_snapshot.values)
        except Exception:
            pass
        return None

    async def run(
        self,
        state: RecoveryState,
    ) -> dict[str, Any]:
        graph = self._require_graph()

        config = {
            "configurable": {
                "thread_id": state["incident_id"],
            }
        }

        try:
            return await graph.ainvoke(
                state,
                config=config,
            )
        except Exception as exc:
            from backend.db.models import IncidentStatus
            from backend.services.incidents import update_incident_state

            try:
                await update_incident_state(
                    incident_id=state["incident_id"],
                    status=IncidentStatus.FAILED,
                )
            except Exception:
                pass

            await telemetry_manager.publish(
                incident_id=state["incident_id"],
                event_type="node_failed",
                node_name="recovery_runtime",
                message=(
                    f"Recovery graph execution failed: {exc}"
                ),
                reasoning=str(exc),
                metadata={
                    "exception_type": type(exc).__name__,
                    "error": str(exc),
                },
                retry_count=state["retry_count"],
            )
            raise

    async def resume(
        self,
        *,
        incident_id: str,
        approved: bool,
    ) -> dict[str, Any]:
        graph = self._require_graph()

        config = {
            "configurable": {
                "thread_id": incident_id,
            }
        }

        return await graph.ainvoke(
            Command(
                resume=approved,
            ),
            config=config,
        )

    async def resume_to_pr_creator(
        self,
        *,
        incident_id: str,
    ) -> dict[str, Any]:
        return await self.resume(incident_id=incident_id, approved=True)


recovery_runtime = RecoveryRuntime()
