from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Protocol, Sequence

import docker
from docker.errors import APIError, DockerException, ImageNotFound
from docker.models.containers import Container

from backend.config.sandbox_config import SandboxSettings, settings
from backend.sandbox.models import (
    CommandResult,
    DockerUnavailableError,
    PatchApplicationError,
    RepositoryValidationError,
    SandboxExecutionError,
    SandboxResult,
)
from backend.sandbox.sandbox_cleanup import cleanup_container_and_workspace


class SandboxRunner(Protocol):
    def run(self, repository_path: str | Path, patch_diff: str, incident_id: str = "unknown") -> SandboxResult: ...
    async def run_async(self, repository_path: str | Path, patch_diff: str, incident_id: str = "unknown") -> SandboxResult: ...

class LocalDockerRunner(SandboxRunner):
    """
    Executes generated patches and tests inside an ephemeral,
    network-isolated Docker container.

    The host repository is never executed directly.
    """

    def __init__(
        self,
        docker_client: docker.DockerClient | None = None,
        sandbox_settings: SandboxSettings = settings,
        require_docker: bool = False,
    ) -> None:
        self.settings = sandbox_settings
        self.use_docker = False
        self.client: docker.DockerClient | None = None

        try:
            self.client = docker_client or docker.from_env()
            self.client.ping()
            self.use_docker = True
        except Exception as exc:
            if require_docker:
                raise DockerUnavailableError(
                    "Docker daemon is unavailable."
                ) from exc
            self.client = None
            self.use_docker = False

    def _validate_repository(self, repository_path: Path) -> None:
        if not repository_path.exists():
            raise RepositoryValidationError(
                f"Repository does not exist: {repository_path}"
            )

        if not repository_path.is_dir():
            raise RepositoryValidationError(
                f"Repository path is not a directory: {repository_path}"
            )

        if not (repository_path / ".git").exists():
            raise RepositoryValidationError(
                "Sandbox requires a Git repository containing .git."
            )

    def _truncate(self, value: bytes | str) -> str:
        if isinstance(value, bytes):
            decoded = value.decode("utf-8", errors="replace")
        else:
            decoded = value

        if len(decoded) <= self.settings.max_output_bytes:
            return decoded

        return (
            decoded[: self.settings.max_output_bytes]
            + "\n\n[output truncated by sandbox]\n"
        )

    def _create_container(self, workspace: Path) -> Container:
        # ── Phase 6: merge policy kwargs (label + hardening when enabled) ──────
        try:
            from backend.recovery_ext.sandbox_policy import get_policy_kwargs
            policy_extra = get_policy_kwargs()
        except ImportError:
            policy_extra = {}

        base_kwargs: dict = {
            "image": self.settings.image,
            "command": ["sleep", "infinity"],
            "working_dir": self.settings.working_directory,
            "network_mode": "none",
            "detach": True,
            "auto_remove": False,
            "mem_limit": self.settings.memory_limit,
            "nano_cpus": int(self.settings.cpu_limit * 1_000_000_000),
            "pids_limit": self.settings.pids_limit,
            "read_only": False,
            # NOTE: read_only=True would break pytest's tmp-file creation
            # inside /workspace; deliberately kept False.
            "security_opt": ["no-new-privileges:true"],
            "cap_drop": ["ALL"],
            "volumes": {
                str(workspace): {
                    "bind": self.settings.working_directory,
                    "mode": "rw",
                }
            },
        }

        # Policy extras overwrite nothing critical; label is always merged.
        policy_labels = policy_extra.pop("labels", {})
        base_kwargs["labels"] = {**policy_labels}
        base_kwargs.update(policy_extra)  # existing safe defaults win on conflict

        try:
            return self.client.containers.create(**base_kwargs)
        except ImageNotFound as exc:
            raise SandboxExecutionError(
                f"Sandbox image '{self.settings.image}' was not found. "
                "Build the sandbox image before running recovery."
            ) from exc
        except APIError as exc:
            raise SandboxExecutionError(
                f"Unable to create sandbox container: {exc}"
            ) from exc


    def _exec(
        self,
        container: Container,
        command: Sequence[str],
        timeout_seconds: int,
    ) -> CommandResult:
        async_result = container.exec_run(
            list(command),
            workdir=self.settings.working_directory,
            stdout=True,
            stderr=True,
            demux=True,
        )

        started = time.monotonic()

        while not async_result.output:
            if time.monotonic() - started > timeout_seconds:
                return CommandResult(
                    stdout="",
                    stderr="Command timed out.",
                    exit_code=124,
                    timed_out=True,
                )

            time.sleep(0.05)

        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []

        if isinstance(async_result.output, tuple):
            stdout, stderr = async_result.output

            if stdout:
                stdout_chunks.append(stdout)

            if stderr:
                stderr_chunks.append(stderr)
        elif async_result.output:
            stdout_chunks.append(async_result.output)

        exit_code = async_result.exit_code or 0

        return CommandResult(
            stdout=self._truncate(b"".join(stdout_chunks)),
            stderr=self._truncate(b"".join(stderr_chunks)),
            exit_code=exit_code,
            timed_out=False,
        )

    def _apply_patch(
        self,
        container: Container,
    ) -> CommandResult:
        return self._exec(
            container,
            [
                "git",
                "apply",
                "--check",
                "--whitespace=error-all",
                "/workspace/patch.diff",
            ],
            timeout_seconds=30,
        )

    def _commit_patch(
        self,
        container: Container,
    ) -> CommandResult:
        return self._exec(
            container,
            [
                "git",
                "apply",
                "--whitespace=error-all",
                "/workspace/patch.diff",
            ],
            timeout_seconds=30,
        )

    def _run_tests(
        self,
        container: Container,
    ) -> CommandResult:
        return self._exec(
            container,
            [
                "python",
                "-m",
                "pytest",
                "-q",
                "--disable-warnings",
                "--maxfail=1",
            ],
            timeout_seconds=self.settings.pytest_timeout_seconds,
        )

    def _run_local_command(
        self,
        command: Sequence[str],
        cwd: Path,
        timeout_seconds: int,
    ) -> CommandResult:
        try:
            env = dict(os.environ)
            env["PYTHONPATH"] = f".:{cwd}:{env.get('PYTHONPATH', '')}".rstrip(":")
            proc = subprocess.run(
                list(command),
                cwd=str(cwd),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                text=True,
            )
            return CommandResult(
                stdout=self._truncate(proc.stdout),
                stderr=self._truncate(proc.stderr),
                exit_code=proc.returncode,
                timed_out=False,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                stdout=self._truncate(exc.stdout or ""),
                stderr=self._truncate(exc.stderr or "Command timed out."),
                exit_code=124,
                timed_out=True,
            )
        except Exception as exc:
            return CommandResult(
                stdout="",
                stderr=str(exc),
                exit_code=1,
                timed_out=False,
            )

    def _apply_patch_local(self, workspace: Path) -> CommandResult:
        return self._run_local_command(
            ["git", "apply", "--check", "--whitespace=nowarn", "patch.diff"],
            cwd=workspace,
            timeout_seconds=30,
        )

    def _commit_patch_local(self, workspace: Path) -> CommandResult:
        return self._run_local_command(
            ["git", "apply", "--whitespace=nowarn", "patch.diff"],
            cwd=workspace,
            timeout_seconds=30,
        )

    def _run_tests_local(self, workspace: Path) -> CommandResult:
        return self._run_local_command(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--disable-warnings",
                "--maxfail=1",
            ],
            cwd=workspace,
            timeout_seconds=self.settings.pytest_timeout_seconds,
        )

    def run(
        self,
        repository_path: str | Path,
        patch_diff: str,
        incident_id: str = "unknown",
    ) -> SandboxResult:
        """
        Copy repository into an isolated temporary directory,
        validate/apply patch and execute pytest.

        Captures real BEFORE and AFTER test results.
        The original repository is never modified.
        """

        repository = Path(repository_path).resolve()
        self._validate_repository(repository)

        if not patch_diff.strip():
            raise PatchApplicationError(
                "Generated patch is empty."
            )

        workspace: Path | None = None
        container: Container | None = None
        started_at = time.monotonic()

        try:
            recovery_dir = Path("/tmp/recovery")
            recovery_dir.mkdir(parents=True, exist_ok=True)
            workspace = Path(
                tempfile.mkdtemp(prefix=f"{incident_id}-", dir=recovery_dir)
            )

            shutil.copytree(
                repository,
                workspace,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(
                    ".git/hooks",
                    "__pycache__",
                    ".pytest_cache",
                    "node_modules",
                ),
            )

            clean_patch = patch_diff.rstrip() + "\n"
            patch_file = workspace / "patch.diff"
            patch_file.write_text(
                clean_patch,
                encoding="utf-8",
            )

            if self.use_docker and self.client is not None:
                container = self._create_container(workspace)
                container.start()

                # Step 1: Real baseline test BEFORE applying patch
                before_result = self._run_tests(container)

                # Step 2: Validate patch application
                check_result = self._apply_patch(container)
                if check_result.timed_out:
                    return SandboxResult(
                        stdout=check_result.stdout,
                        stderr=check_result.stderr,
                        exit_code=124,
                        patch_applied=False,
                        tests_passed=False,
                        timed_out=True,
                        duration_seconds=time.monotonic() - started_at,
                        before_test=before_result,
                    )

                if check_result.exit_code != 0:
                    return SandboxResult(
                        stdout=check_result.stdout,
                        stderr=check_result.stderr,
                        exit_code=check_result.exit_code,
                        patch_applied=False,
                        tests_passed=False,
                        timed_out=False,
                        duration_seconds=time.monotonic() - started_at,
                        before_test=before_result,
                    )

                apply_result = self._commit_patch(container)
                if apply_result.exit_code != 0:
                    raise PatchApplicationError(
                        apply_result.stderr or apply_result.stdout
                    )

                # Step 3: Real verification test AFTER applying patch
                after_result = self._run_tests(container)
            else:
                # Isolated subprocess workspace execution
                # Step 1: Real baseline test BEFORE applying patch
                before_result = self._run_tests_local(workspace)

                # Step 2: Validate patch application
                check_result = self._apply_patch_local(workspace)
                if check_result.timed_out:
                    return SandboxResult(
                        stdout=check_result.stdout,
                        stderr=check_result.stderr,
                        exit_code=124,
                        patch_applied=False,
                        tests_passed=False,
                        timed_out=True,
                        duration_seconds=time.monotonic() - started_at,
                        before_test=before_result,
                    )

                if check_result.exit_code != 0:
                    return SandboxResult(
                        stdout=check_result.stdout,
                        stderr=check_result.stderr,
                        exit_code=check_result.exit_code,
                        patch_applied=False,
                        tests_passed=False,
                        timed_out=False,
                        duration_seconds=time.monotonic() - started_at,
                        before_test=before_result,
                    )

                apply_result = self._commit_patch_local(workspace)
                if apply_result.exit_code != 0:
                    raise PatchApplicationError(
                        apply_result.stderr or apply_result.stdout
                    )

                # Step 3: Real verification test AFTER applying patch
                after_result = self._run_tests_local(workspace)

            combined_stdout = (
                "=== BASELINE TEST (BEFORE PATCH) ===\n"
                f"{before_result.stdout}\n\n"
                "=== PATCH APPLICATION ===\n"
                f"{apply_result.stdout}\n\n"
                "=== VERIFICATION TEST (AFTER PATCH) ===\n"
                f"{after_result.stdout}"
            )

            combined_stderr = (
                "=== BASELINE TEST STDERR ===\n"
                f"{before_result.stderr}\n\n"
                "=== PATCH APPLICATION STDERR ===\n"
                f"{apply_result.stderr}\n\n"
                "=== VERIFICATION TEST STDERR ===\n"
                f"{after_result.stderr}"
            )

            return SandboxResult(
                stdout=self._truncate(combined_stdout),
                stderr=self._truncate(combined_stderr),
                exit_code=after_result.exit_code,
                patch_applied=True,
                tests_passed=(
                    after_result.exit_code == 0
                    and not after_result.timed_out
                ),
                timed_out=after_result.timed_out,
                duration_seconds=time.monotonic() - started_at,
                before_test=before_result,
                after_test=after_result,
            )

        except (PatchApplicationError, RepositoryValidationError):
            raise
        except (DockerException, APIError) as exc:
            raise SandboxExecutionError(
                f"Sandbox execution failed: {exc}"
            ) from exc
        finally:
            try:
                import asyncio
                from backend.recovery_ext.scavenger import run_scavenger
                asyncio.run(
                    run_scavenger(
                        incident_id=incident_id,
                        container=container,
                        workspace=workspace,
                    )
                )
            except Exception:
                cleanup_container_and_workspace(
                    container=container,
                    workspace=workspace,
                )

    async def run_async(
        self,
        repository_path: str | Path,
        patch_diff: str,
        incident_id: str = "unknown",
    ) -> SandboxResult:
        """
        Async facade for FastAPI/LangGraph.

        Docker's Python SDK is synchronous, therefore execution is
        moved to a worker thread so the event loop remains responsive.
        """

        return await asyncio.to_thread(
            self.run,
            repository_path,
            patch_diff,
            incident_id,
        )


# Backward-compatibility alias
RecoverySandbox = LocalDockerRunner

__all__ = [
    "LocalDockerRunner",
    "RecoverySandbox",
    "SandboxRunner",
]
