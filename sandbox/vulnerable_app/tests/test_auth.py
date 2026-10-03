# sandbox/vulnerable_app/tests/test_auth.py

from __future__ import annotations

import pytest

from sandbox.vulnerable_app.auth import authenticate


def test_valid_payload_authenticates() -> None:
    result = authenticate(
        {
            "user_id": "demo-user",
        }
    )

    assert result == {
        "authenticated": True,
        "user_id": "demo-user",
    }


def test_payload_requires_user_id() -> None:
    """
    This test documents the intended post-recovery contract.

    The current vulnerable implementation fails here with KeyError.
    The repaired implementation should instead raise ValueError.
    """

    with pytest.raises(ValueError, match="user_id is required"):
        authenticate({})


def test_missing_user_id_reproduces_original_regression() -> None:
    """
    Explicitly captures the original failure signature.

    This test is useful for validating the sandbox before the generated
    patch is applied.
    """

    with pytest.raises(KeyError, match="user_id"):
        authenticate({"email": "demo@example.com"})


def test_none_payload_is_rejected() -> None:
    with pytest.raises((TypeError, ValueError)):
        authenticate(None)  # type: ignore[arg-type]


def test_empty_user_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="user_id"):
        authenticate({"user_id": ""})


def test_whitespace_user_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="user_id"):
        authenticate({"user_id": "   "})
