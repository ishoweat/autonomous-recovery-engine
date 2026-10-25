from __future__ import annotations

import httpx
import logging

logger = logging.getLogger(__name__)

_SHARED_HTTP_CLIENT: httpx.AsyncClient | None = None


def get_shared_client() -> httpx.AsyncClient:
    """
    Return a shared persistent httpx.AsyncClient for connection pooling and TLS session reuse.
    Recreating clients on every request introduces significant handshake and connection latency.
    """
    global _SHARED_HTTP_CLIENT
    if _SHARED_HTTP_CLIENT is None or _SHARED_HTTP_CLIENT.is_closed:
        _SHARED_HTTP_CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=30, max_connections=100),
            follow_redirects=True,
        )
    return _SHARED_HTTP_CLIENT


async def close_shared_client() -> None:
    """Close the shared persistent httpx.AsyncClient on application shutdown."""
    global _SHARED_HTTP_CLIENT
    if _SHARED_HTTP_CLIENT is not None and not _SHARED_HTTP_CLIENT.is_closed:
        try:
            await _SHARED_HTTP_CLIENT.aclose()
        except Exception as exc:
            logger.warning("Error closing shared HTTP client: %s", exc)
        finally:
            _SHARED_HTTP_CLIENT = None
