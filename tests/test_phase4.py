import pytest
from pathlib import Path
import tempfile

from backend.config.sandbox_config import SandboxSettings
from backend.sandbox.models import (
    CommandResult,
    SandboxResult,
    RepositoryValidationError,
    PatchApplicationError,
)
from backend.sandbox.sandbox import RecoverySandbox
from backend.integrations.github_branch import create_recovery_branch_name
from backend.integrations.github_pr import build_recovery_pr_body


def test_sandbox_settings_defaults():
    settings = SandboxSettings.from_environment()
    assert settings.working_directory == "/workspace"
    assert settings.timeout_seconds > 0
    assert settings.memory_limit == "512m"


def test_branch_name_generator():
    branch = create_recovery_branch_name("inc-abc-123!@#", retry_count=2)
    assert branch == "recovery/incident-inc-abc-123-retry-2"


def test_pr_body_builder():
    pr_body = build_recovery_pr_body(
        incident_id="inc-100",
        root_cause={"summary": "Missing user_id check"},
        risk={"score": 0.45, "decision": "APPROVE", "breakdown": ["auth_file (0.35)"]},
        test_results={"exit_code": 0, "tests_passed": True, "timed_out": False},
        patch_diff="--- a/auth.py\n+++ b/auth.py\n+ check"
    )
    assert "## Autonomous Recovery Engine" in pr_body
    assert "`inc-100`" in pr_body
    assert "**Score:** `0.4500`" in pr_body
    assert "Missing user_id check" in pr_body


def test_repository_validation():
    with tempfile.TemporaryDirectory() as tmpdir:
        non_git_dir = Path(tmpdir)
        # Sandbox requires docker daemon or fails on init if Docker is unavailable
        try:
            sandbox = RecoverySandbox()
            with pytest.raises(RepositoryValidationError):
                sandbox.run(non_git_dir, "some patch")
        except Exception as exc:
            # If Docker daemon is not active on local host environment, DockerUnavailableError is expected
            assert "Docker daemon is unavailable" in str(exc) or "Repository requires a Git repository" in str(exc) or "does not exist" in str(exc)
