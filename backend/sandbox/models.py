from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


@dataclass(frozen=True, slots=True)
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    patch_applied: bool
    tests_passed: bool
    timed_out: bool
    duration_seconds: float
    before_test: CommandResult | None = None
    after_test: CommandResult | None = None


class SandboxError(RuntimeError):
    """Base class for sandbox failures."""


class DockerUnavailableError(SandboxError):
    """Raised when Docker cannot be reached."""


class SandboxConfigurationError(SandboxError):
    """Raised when the sandbox configuration is invalid."""


class SandboxExecutionError(SandboxError):
    """Raised when sandbox execution cannot be completed."""


class PatchApplicationError(SandboxError):
    """Raised when git apply rejects the generated patch."""


class RepositoryValidationError(SandboxError):
    """Raised when a repository cannot safely be prepared."""
