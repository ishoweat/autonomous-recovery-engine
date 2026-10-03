from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class GitHubSettings:
    token: str
    app_name: str = "Autonomous Recovery Engine"
    default_branch: str = "main"

    @classmethod
    def from_environment(cls) -> GitHubSettings:
        token = os.getenv("GITHUB_TOKEN", "").strip()

        if not token:
            raise RuntimeError(
                "GITHUB_TOKEN environment variable is required."
            )

        return cls(
            token=token,
            app_name=os.getenv(
                "GITHUB_APP_NAME",
                "Autonomous Recovery Engine",
            ),
            default_branch=os.getenv(
                "GITHUB_DEFAULT_BRANCH",
                "main",
            ),
        )
