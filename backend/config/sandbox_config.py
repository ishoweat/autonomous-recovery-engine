from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class SandboxSettings:
    image: str
    timeout_seconds: int
    memory_limit: str
    cpu_limit: float
    pids_limit: int
    pytest_timeout_seconds: int
    working_directory: str
    max_output_bytes: int

    @classmethod
    def from_environment(cls) -> SandboxSettings:
        return cls(
            image=os.getenv(
                "RECOVERY_SANDBOX_IMAGE",
                "autonomous-recovery-sandbox:py311-alpine",
            ),
            timeout_seconds=int(
                os.getenv("RECOVERY_SANDBOX_TIMEOUT_SECONDS", "120")
            ),
            memory_limit=os.getenv(
                "RECOVERY_SANDBOX_MEMORY_LIMIT",
                "512m",
            ),
            cpu_limit=float(
                os.getenv("RECOVERY_SANDBOX_CPU_LIMIT", "1.0")
            ),
            pids_limit=int(
                os.getenv("RECOVERY_SANDBOX_PIDS_LIMIT", "128")
            ),
            pytest_timeout_seconds=int(
                os.getenv("RECOVERY_PYTEST_TIMEOUT_SECONDS", "90")
            ),
            working_directory="/workspace",
            max_output_bytes=int(
                os.getenv("RECOVERY_SANDBOX_MAX_OUTPUT_BYTES", "200000")
            ),
        )


settings = SandboxSettings.from_environment()
