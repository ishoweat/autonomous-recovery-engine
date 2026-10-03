"""
recovery_ext/scavenger.py
──────────────────────────
Phase 6: Post-run Scavenger.

Responsibilities (in finally path after every sandbox run):
  1. Force-remove the sandbox container (belt-and-suspenders over baseline cleanup).
  2. Remove temp workspace directories.
  3. Sweep orphaned containers labelled `are-sandbox` older than N minutes.
  4. Emit `[SCAVENGER]` telemetry event.

Usage (from sandbox finally block):
    from backend.recovery_ext.scavenger import run_scavenger
    await run_scavenger(
        incident_id=incident_id,
        container=container,    # may be None
        workspace=workspace,    # may be None
        retry_count=retry_count,
    )
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from docker.models.containers import Container

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

ORPHAN_MAX_AGE_SECONDS: int = int(os.environ.get("SCAVENGER_ORPHAN_AGE_SECONDS", "600"))

# Import the label from sandbox_policy so it is the single source of truth.
try:
    from backend.recovery_ext.sandbox_policy import SANDBOX_LABEL
except ImportError:
    SANDBOX_LABEL = "are-sandbox"


# ──────────────────────────────────────────────────────────────────────────────
# Low-level helpers (synchronous — called in thread executor by run_scavenger)
# ──────────────────────────────────────────────────────────────────────────────

def _force_remove_container(container: "Container | None") -> bool:
    """Force-remove a container. Returns True if actually removed."""
    if container is None:
        return False
    try:
        container.remove(force=True)
        logger.debug("[SCAVENGER] container %s removed.", getattr(container, "name", "?"))
        return True
    except Exception as exc:
        # NotFound is fine — already gone
        if "404" not in str(exc) and "NotFound" not in type(exc).__name__:
            logger.warning("[SCAVENGER] container remove failed (non-fatal): %s", exc)
        return False


def _remove_workspace(workspace: "Path | str | None") -> bool:
    """Remove a temp workspace directory. Returns True if removed."""
    if workspace is None:
        return False
    try:
        ws = Path(workspace)
        if ws.exists():
            shutil.rmtree(ws, ignore_errors=True)
            logger.debug("[SCAVENGER] workspace %s removed.", ws)
            return True
    except Exception as exc:
        logger.warning("[SCAVENGER] workspace remove failed (non-fatal): %s", exc)
    return False


def _sweep_orphans(*, older_than_seconds: int = ORPHAN_MAX_AGE_SECONDS) -> int:
    """
    Find and remove containers with label `are-sandbox` older than N seconds.
    Returns the number of orphans removed.
    """
    removed = 0
    try:
        import docker
        from docker.errors import DockerException, NotFound

        client = docker.from_env()
        now = time.time()

        containers = client.containers.list(
            all=True,
            filters={"label": SANDBOX_LABEL},
        )

        for container in containers:
            try:
                raw_created = container.attrs.get("Created", "")
                if not raw_created:
                    container.remove(force=True)
                    removed += 1
                    continue

                created = str(raw_created)
                if created.endswith("Z"):
                    created = created[:-1] + "+00:00"

                from datetime import datetime
                created_dt = datetime.fromisoformat(created)
                age = now - created_dt.timestamp()

                if age >= older_than_seconds:
                    container.remove(force=True)
                    removed += 1
                    logger.info("[SCAVENGER] swept orphan %s (age=%.0fs)", container.name, age)

            except NotFound:
                continue
            except Exception as exc:
                logger.warning("[SCAVENGER] orphan sweep error for %s: %s", getattr(container, "name", "?"), exc)

    except Exception as exc:
        # Docker not available — silently skip
        logger.debug("[SCAVENGER] orphan sweep skipped (Docker unavailable): %s", exc)

    return removed


def _sync_scavenge(
    container: "Any | None",
    workspace: "Any | None",
    older_than_seconds: int,
) -> tuple[bool, bool, int]:
    """
    Synchronous entry: remove container, workspace, orphans.
    Returns (container_removed, workspace_removed, orphans_removed).
    """
    container_removed = _force_remove_container(container)
    workspace_removed = _remove_workspace(workspace)
    orphans_removed = _sweep_orphans(older_than_seconds=older_than_seconds)
    return container_removed, workspace_removed, orphans_removed


# ──────────────────────────────────────────────────────────────────────────────
# Async entry point
# ──────────────────────────────────────────────────────────────────────────────

async def run_scavenger(
    *,
    incident_id: str,
    container: "Any | None" = None,
    workspace: "Any | None" = None,
    retry_count: int = 0,
    older_than_seconds: int = ORPHAN_MAX_AGE_SECONDS,
) -> None:
    """
    Run all scavenger steps asynchronously.

    Safe to call even when container/workspace are None.
    Never raises — all errors are logged and swallowed.
    """
    import asyncio
    try:
        container_removed, workspace_removed, orphans_removed = (
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _sync_scavenge(container, workspace, older_than_seconds),
            )
        )
    except Exception as exc:
        logger.error("[SCAVENGER] unexpected error: %s", exc)
        container_removed = workspace_removed = False
        orphans_removed = 0

    # Emit telemetry event
    message = (
        f"[SCAVENGER] container {'removed' if container_removed else 'N/A'}, "
        f"temp {'cleaned' if workspace_removed else 'N/A'}, "
        f"orphans swept: {orphans_removed}"
    )
    logger.info(message)

    try:
        from backend.orchestration.telemetry import emit_node_event
        await emit_node_event(
            incident_id=incident_id,
            event_type="scavenger_completed",
            node_name="scavenger",
            message=message,
            metadata={
                "container_removed": container_removed,
                "workspace_removed": workspace_removed,
                "orphans_swept": orphans_removed,
                "stage": "cleanup",
            },
            retry_count=retry_count,
        )
    except Exception as exc:
        logger.warning("[SCAVENGER] telemetry emit failed (non-fatal): %s", exc)
