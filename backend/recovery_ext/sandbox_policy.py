"""
recovery_ext/sandbox_policy.py
───────────────────────────────
Phase 6: Canonical sandbox security policy.

Centralises all hardening knobs behind ENABLE_SANDBOX_HARDENING.

The policy is a *delta* — it returns extra kwargs that are merged into
the existing containers.create() call inside RecoverySandbox._create_container.
Nothing is removed from the baseline; only additive options are applied.

If any knob causes a DockerException during container creation the caller
MUST catch it, log which option failed, and re-try WITHOUT that option.
This module exports `get_policy_kwargs()` and `SANDBOX_LABEL` for
downstream use.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Label applied to every container so the scavenger can sweep orphans.
SANDBOX_LABEL = "are-sandbox"

# Human-readable spec string shown in the UI.
SANDBOX_SPEC_DISPLAY = "Ephemeral Alpine-Py · Net: NONE · RAM: 512M · CPU: 1.0"


def get_policy_kwargs(*, hardening_enabled: bool | None = None) -> dict[str, Any]:
    """
    Return container-create kwargs that enforce the Phase 6 sandbox policy.

    When ENABLE_SANDBOX_HARDENING is false the dict is empty — the
    existing baseline in _create_container already provides a safe default.

    When true, the returned dict is **merged** into the existing kwargs
    (caller takes precedence on any key conflict so existing safe settings
    are never silently weakened).
    """
    if hardening_enabled is None:
        hardening_enabled = os.environ.get("ENABLE_SANDBOX_HARDENING", "false").lower() in ("true", "1", "yes")

    if not hardening_enabled:
        # Even without hardening, always attach the label for scavenger.
        return {"labels": {SANDBOX_LABEL: "true"}}

    # ── Hardened policy ─────────────────────────────────────────────────────
    # All values are sourced from env so operators can tune without code changes.
    mem_limit: str = os.environ.get("RECOVERY_SANDBOX_MEMORY_LIMIT", "512m")
    cpu_limit: float = float(os.environ.get("RECOVERY_SANDBOX_CPU_LIMIT", "1.0"))
    pids_limit: int = int(os.environ.get("RECOVERY_SANDBOX_PIDS_LIMIT", "128"))
    timeout: int = int(os.environ.get("RECOVERY_SANDBOX_TIMEOUT_SECONDS", "120"))

    return {
        # Networking
        "network_mode": "none",
        # Memory
        "mem_limit": mem_limit,
        "memswap_limit": mem_limit,   # disable swap
        # CPU (1 full core)
        "nano_cpus": int(cpu_limit * 1_000_000_000),
        # Process isolation
        "pids_limit": pids_limit,
        # Privilege reduction
        "security_opt": ["no-new-privileges:true"],
        "cap_drop": ["ALL"],
        # read_only=True breaks pytest temp-file creation inside /workspace;
        # we intentionally skip it and document why.
        # Scavenger label
        "labels": {
            SANDBOX_LABEL: "true",
            "are-sandbox-timeout": str(timeout),
        },
    }


def policy_display_lines() -> list[str]:
    """Return human-readable policy lines for the UI sandbox card."""
    return [
        f"Net: NONE",
        f"RAM: {os.environ.get('RECOVERY_SANDBOX_MEMORY_LIMIT', '512m').upper()}",
        f"CPU: {float(os.environ.get('RECOVERY_SANDBOX_CPU_LIMIT', '1.0')):.1f}",
        f"PIDs: {os.environ.get('RECOVERY_SANDBOX_PIDS_LIMIT', '128')}",
        f"Timeout: {os.environ.get('RECOVERY_SANDBOX_TIMEOUT_SECONDS', '120')}s",
        "Cap: ALL dropped",
        "NoNewPrivileges: true",
    ]
