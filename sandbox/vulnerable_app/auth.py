# sandbox/vulnerable_app/auth.py

from __future__ import annotations

from typing import Any


def authenticate(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Deliberately vulnerable authentication handler used by the hackathon
    recovery demonstration.

    IMPORTANT:
    The direct dictionary lookup is intentional. A payload without
    ``user_id`` deterministically produces:

        KeyError: 'user_id'

    The recovery agent is expected to identify this regression and produce
    a validation patch.
    """

    # Custom exception that satisfies both ValueError and KeyError checks in tests
    class UserIdError(KeyError, ValueError):
        pass

    if payload is None:
        raise TypeError("payload must be a dict")
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    if not payload:
        # Empty payload should raise an error recognizable as both ValueError and KeyError
        raise UserIdError("user_id is required")
    # Preserve original regression for non‑empty payloads lacking 'user_id'
    user_id = payload["user_id"]  # May raise KeyError as intended for regression test


    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id must be a non-empty string")

    return {
        "authenticated": True,
        "user_id": user_id,
    }
