# backend/tools/sandbox_cleanup.py

from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import docker
from docker.errors import APIError, DockerException, NotFound
from docker.models.containers import Container

logger = logging.getLogger(__name__)


SANDBOX_PREFIX = "recovery-sandbox-"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MEMORY_LIMIT = "512m"
DEFAULT_CPU_COUNT = 1.0


@dataclass(slots=True, frozen=True)
class SandboxSecurityConfig:
    """
    Immutable execution policy for recovery containers.
    """

    network_mode: str = "none"
    mem_limit: str = DEFAULT_MEMORY_LIMIT
    cpu_count: float = DEFAULT_CPU_COUNT
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if self.network_mode != "none":
            raise ValueError(
                "Recovery sandboxes must use network_mode='none'"
            )

        if self.mem_limit != DEFAULT_MEMORY_LIMIT:
            raise ValueError(
                "Recovery sandboxes must use a 512m memory limit"
            )

        if self.cpu_count != DEFAULT_CPU_COUNT:
            raise ValueError(
                "Recovery sandboxes must use exactly one CPU"
            )

        if not 1 <= self.timeout_seconds <= 30:
            raise ValueError(
                "Sandbox timeout must be between 1 and 30 seconds"
            )


class SandboxTimeoutError(TimeoutError):
    """Raised when a sandbox exceeds its execution deadline."""


class SandboxExecutionError(RuntimeError):
    """Raised for Docker lifecycle failures."""


class HardenedSandbox:
    """
    Deterministic Docker sandbox lifecycle.

    Security properties:
      * no network
      * 512 MB memory ceiling
      * one CPU
      * 30 second hard deadline
      * forced kill on timeout
      * guaranteed removal on exit
    """

    def __init__(
        self,
        *,
        client: docker.DockerClient | None = None,
        image: str = "python:3.11-alpine",
        config: SandboxSecurityConfig | None = None,
    ) -> None:
        self.client = client or docker.from_env()
        self.image = image
        self.config = config or SandboxSecurityConfig()

        self.container: Container | None = None
        self._lock = threading.RLock()

    def _container_name(self) -> str:
        return (
            f"{SANDBOX_PREFIX}"
            f"{int(time.time() * 1000)}"
            f"-{threading.get_ident()}"
        )

    def create(
        self,
        *,
        command: list[str] | str,
        volumes: dict[str, dict[str, str]] | None = None,
        working_dir: str = "/workspace",
        environment: dict[str, str] | None = None,
    ) -> Container:
        with self._lock:
            if self.container is not None:
                raise SandboxExecutionError(
                    "Sandbox container already exists"
                )

            try:
                self.container = self.client.containers.run(
                    image=self.image,
                    command=command,
                    name=self._container_name(),
                    detach=True,
                    network_mode=self.config.network_mode,
                    mem_limit=self.config.mem_limit,
                    nano_cpus=1_000_000_000,
                    pids_limit=128,
                    working_dir=working_dir,
                    volumes=volumes or {},
                    environment=environment or {},
                    read_only=False,
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges:true"],
                )

                return self.container

            except DockerException as exc:
                self.container = None
                raise SandboxExecutionError(
                    f"Unable to create recovery sandbox: {exc}"
                ) from exc

    def wait(
        self,
        *,
        timeout_seconds: int | None = None,
    ) -> int:
        with self._lock:
            if self.container is None:
                raise SandboxExecutionError(
                    "Sandbox has not been created"
                )

            timeout = (
                timeout_seconds
                if timeout_seconds is not None
                else self.config.timeout_seconds
            )

            if timeout > self.config.timeout_seconds:
                raise ValueError(
                    "Requested timeout exceeds sandbox security policy"
                )

            container = self.container

        result: dict[str, Any] = {}
        error: list[BaseException] = []

        def wait_container() -> None:
            try:
                result["status"] = container.wait(
                    timeout=timeout
                )
            except BaseException as exc:
                error.append(exc)

        thread = threading.Thread(
            target=wait_container,
            daemon=True,
        )

        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            self.kill()

            raise SandboxTimeoutError(
                f"Sandbox exceeded {timeout}s execution deadline"
            )

        if error:
            exc = error[0]

            if isinstance(exc, APIError):
                raise SandboxExecutionError(
                    f"Docker wait failed: {exc}"
                ) from exc

            raise SandboxExecutionError(
                f"Sandbox wait failed: {exc}"
            ) from exc

        status = result.get("status")

        if isinstance(status, dict):
            return int(status.get("StatusCode", 1))

        if isinstance(status, int):
            return status

        raise SandboxExecutionError(
            "Docker returned an invalid container status"
        )

    def logs(self) -> tuple[str, str]:
        with self._lock:
            if self.container is None:
                raise SandboxExecutionError(
                    "Sandbox has not been created"
                )

            try:
                stdout = self.container.logs(
                    stdout=True,
                    stderr=False,
                ).decode(
                    "utf-8",
                    errors="replace",
                )

                stderr = self.container.logs(
                    stdout=False,
                    stderr=True,
                ).decode(
                    "utf-8",
                    errors="replace",
                )

                return stdout, stderr

            except DockerException as exc:
                raise SandboxExecutionError(
                    f"Unable to retrieve sandbox logs: {exc}"
                ) from exc

    def kill(self) -> None:
        with self._lock:
            if self.container is None:
                return

            try:
                self.container.kill()
            except NotFound:
                return
            except DockerException as exc:
                logger.warning(
                    "Unable to kill sandbox %s: %s",
                    self.container.name,
                    exc,
                )

    def remove(self) -> None:
        with self._lock:
            if self.container is None:
                return

            container = self.container
            self.container = None

            try:
                container.remove(
                    force=True
                )
            except NotFound:
                return
            except DockerException as exc:
                logger.warning(
                    "Unable to remove sandbox %s: %s",
                    container.name,
                    exc,
                )

    def __enter__(self) -> HardenedSandbox:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> bool:
        self.remove()
        return False


@contextlib.contextmanager
def sandbox_context(
    *,
    client: docker.DockerClient | None = None,
    image: str = "python:3.11-alpine",
    config: SandboxSecurityConfig | None = None,
    command: list[str] | str,
    volumes: dict[str, dict[str, str]] | None = None,
    working_dir: str = "/workspace",
    environment: dict[str, str] | None = None,
) -> Iterator[HardenedSandbox]:
    """
    Convenience context manager guaranteeing container cleanup.
    """

    sandbox = HardenedSandbox(
        client=client,
        image=image,
        config=config,
    )

    try:
        sandbox.create(
            command=command,
            volumes=volumes,
            working_dir=working_dir,
            environment=environment,
        )

        yield sandbox

    finally:
        sandbox.remove()


def purge_orphaned_sandboxes(
    *,
    client: docker.DockerClient | None = None,
    older_than_seconds: int = 300,
) -> int:
    """
    Delete stale recovery-sandbox-* containers.

    Called during application startup to prevent leaked containers from
    previous crashes/restarts.

    Returns the number of containers removed.
    """

    if older_than_seconds < 0:
        raise ValueError(
            "older_than_seconds must be non-negative"
        )

    try:
        docker_client = client or docker.from_env()
    except Exception as exc:
        logger.info("Docker daemon not available during orphan cleanup: %s", exc)
        return 0

    now = time.time()
    removed = 0

    try:
        containers = docker_client.containers.list(
            all=True,
            filters={
                "name": SANDBOX_PREFIX,
            },
        )
    except DockerException as exc:
        raise SandboxExecutionError(
            f"Unable to enumerate sandbox containers: {exc}"
        ) from exc

    for container in containers:
        try:
            name = container.name or ""

            if not name.startswith(SANDBOX_PREFIX):
                continue

            raw_created = container.attrs.get(
                "Created"
            )

            if not raw_created:
                container.remove(force=True)
                removed += 1
                continue

            created = str(raw_created)

            if created.endswith("Z"):
                created = created[:-1] + "+00:00"

            from datetime import datetime

            created_dt = datetime.fromisoformat(
                created
            )

            created_epoch = created_dt.timestamp()

            if (
                now - created_epoch
                >= older_than_seconds
            ):
                container.remove(force=True)
                removed += 1

        except NotFound:
            continue
        except (
            DockerException,
            ValueError,
            OverflowError,
        ) as exc:
            logger.warning(
                "Unable to clean sandbox container %s: %s",
                getattr(container, "name", "<unknown>"),
                exc,
            )

    return removed


def startup_sandbox_cleanup() -> int:
    """
    Application-startup entrypoint.

    Cleanup failure is intentionally surfaced instead of silently ignored:
    a production deployment should know if stale isolation resources could
    not be removed.
    """

    try:
        removed = purge_orphaned_sandboxes()
    except SandboxExecutionError:
        raise
    except Exception as exc:
        logger.info("Docker sandbox startup cleanup bypassed: %s", exc)
        return 0

    logger.info(
        "Sandbox startup cleanup removed %d stale containers",
        removed,
    )

    return removed


def cleanup_container_and_workspace(
    container: Container | None = None,
    workspace: Any | None = None,
) -> None:
    """
    Safely stop/remove a container and remove a temporary workspace directory.
    """

    if container is not None:
        try:
            container.stop(timeout=1)
        except Exception:
            pass
        try:
            container.remove(force=True)
        except Exception:
            pass

    if workspace is not None:
        try:
            import shutil
            from pathlib import Path
            ws_path = Path(workspace)
            if ws_path.exists():
                shutil.rmtree(ws_path, ignore_errors=True)
        except Exception:
            pass

