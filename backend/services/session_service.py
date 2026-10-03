from __future__ import annotations

import json
import logging
import os
import secrets
import time
from typing import Any, Dict, List, Optional
import httpx

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None

try:
    import fakeredis.aioredis
except ImportError:
    fakeredis = None

logger = logging.getLogger(__name__)

SESSION_PREFIX = "session:"
USER_SESSIONS_PREFIX = "user_sessions:"
DEFAULT_SESSION_TTL = 3600  # 1 hour default TTL


class InMemoryRedisClient:
    """Zero-dependency in-memory Redis client with TTL expiration support."""
    def __init__(self):
        self._data: Dict[str, str] = {}
        self._expires: Dict[str, float] = {}

    async def ping(self):
        return True

    async def set(self, key: str, value: str, ex: Optional[int] = None):
        self._data[key] = value
        if ex is not None:
            self._expires[key] = time.time() + ex
        elif key in self._expires:
            del self._expires[key]
        return True

    async def get(self, key: str) -> Optional[str]:
        if key in self._expires and time.time() >= self._expires[key]:
            self._data.pop(key, None)
            self._expires.pop(key, None)
            return None
        return self._data.get(key)

    async def delete(self, key: str) -> int:
        self._expires.pop(key, None)
        return 1 if self._data.pop(key, None) is not None else 0

    async def ttl(self, key: str) -> int:
        if key not in self._data:
            return -2
        if key not in self._expires:
            return -1
        rem = self._expires[key] - time.time()
        if rem <= 0:
            self._data.pop(key, None)
            self._expires.pop(key, None)
            return -2
        return int(rem)


class SessionService:
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.default_ttl = int(os.getenv("SESSION_TTL_SECONDS", str(DEFAULT_SESSION_TTL)))
        self._client: Optional[Any] = None
        self._using_fakeredis = False

    async def get_client(self) -> Any:
        if self._client is not None:
            return self._client

        if aioredis is not None:
            try:
                client = aioredis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_timeout=2.0,
                    socket_connect_timeout=2.0,
                )
                await client.ping()
                self._client = client
                self._using_fakeredis = False
                logger.info("Connected to Redis server at %s", self.redis_url)
                return self._client
            except Exception as err:
                logger.warning(
                    "Redis server unavailable (%s). Falling back to local Redis engine.",
                    err,
                )

        if fakeredis is not None:
            try:
                self._client = fakeredis.aioredis.FakeRedis(decode_responses=True)
                self._using_fakeredis = True
                return self._client
            except Exception:
                pass

        self._client = InMemoryRedisClient()
        self._using_fakeredis = True
        return self._client

    async def create_session(
        self,
        github_user_data: Dict[str, Any],
        access_token: str,
        ttl: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a unique temporary session stored in Redis with expiration, strictly tied to user."""
        client = await self.get_client()

        session_id = f"sess_{secrets.token_urlsafe(32)}"
        session_ttl = ttl if ttl is not None else self.default_ttl

        now = time.time()
        expires_at = now + session_ttl

        user_id = github_user_data.get("id")
        username = github_user_data.get("login") or f"user_{user_id}"
        display_name = github_user_data.get("name") or username
        avatar_url = github_user_data.get("avatar_url") or ""

        session_payload = {
            "session_id": session_id,
            "user_id": user_id,
            "username": username,
            "display_name": display_name,
            "avatar_url": avatar_url,
            "access_token": access_token,
            "created_at": now,
            "expires_at": expires_at,
            "ttl": session_ttl,
        }

        key = f"{SESSION_PREFIX}{session_id}"
        # Save session object in Redis with expiration (TTL)
        await client.set(key, json.dumps(session_payload), ex=session_ttl)

        # Track session ID under user index for per-user lookup/isolation
        user_key = f"{USER_SESSIONS_PREFIX}{username}"
        try:
            existing = await client.get(user_key)
            sess_list = json.loads(existing) if existing else []
            if session_id not in sess_list:
                sess_list.append(session_id)
            await client.set(user_key, json.dumps(sess_list), ex=session_ttl * 2)
        except Exception as e:
            logger.warning("Failed to update user session index: %s", e)

        logger.info("Created GitHub Redis session %s for user %s (TTL: %ds)", session_id, username, session_ttl)
        return session_payload

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve active session from Redis. Returns None if missing or expired."""
        if not session_id:
            return None

        client = await self.get_client()
        key = f"{SESSION_PREFIX}{session_id}"

        raw_data = await client.get(key)
        if not raw_data:
            return None

        try:
            session_data = json.loads(raw_data)
            now = time.time()
            expires_at = session_data.get("expires_at", 0)

            if now >= expires_at:
                # Session has expired - securely delete it immediately
                await self.delete_session(session_id)
                return None

            ttl_remaining = await client.ttl(key)
            if ttl_remaining <= 0:
                await self.delete_session(session_id)
                return None

            session_data["ttl_remaining"] = max(0, int(ttl_remaining))
            return session_data
        except Exception as err:
            logger.error("Error decoding Redis session data for %s: %s", session_id, err)
            return None

    async def delete_session(self, session_id: str) -> bool:
        """Securely delete a temporary session from Redis immediately on logout or expiration."""
        if not session_id:
            return False

        client = await self.get_client()
        key = f"{SESSION_PREFIX}{session_id}"

        # Fetch session first to get username for index cleanup
        raw_data = await client.get(key)
        username = None
        if raw_data:
            try:
                data = json.loads(raw_data)
                username = data.get("username")
            except Exception:
                pass

        # Delete key from Redis
        result = await client.delete(key)

        if username:
            user_key = f"{USER_SESSIONS_PREFIX}{username}"
            try:
                existing = await client.get(user_key)
                if existing:
                    sess_list = json.loads(existing)
                    if session_id in sess_list:
                        sess_list.remove(session_id)
                        if sess_list:
                            await client.set(user_key, json.dumps(sess_list))
                        else:
                            await client.delete(user_key)
            except Exception:
                pass

        logger.info("Deleted Redis session %s (User: %s)", session_id, username)
        return bool(result)

    async def get_session_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Alias for get_session to support ID-based lookup."""
        return await self.get_session(session_id)

    async def get_token_for_user(self, username: str) -> Optional[str]:
        """Retrieve a valid, unexpired GitHub access token for the given username."""
        if not username:
            return None
        client = await self.get_client()
        user_key = f"{USER_SESSIONS_PREFIX}{username}"
        try:
            raw_sessions = await client.get(user_key)
            if not raw_sessions:
                return None
            session_ids = json.loads(raw_sessions)
            for sess_id in reversed(session_ids):
                sess = await self.get_session(sess_id)
                if sess and sess.get("access_token"):
                    return str(sess["access_token"])
        except Exception as err:
            logger.warning("Error fetching token for user %s: %s", username, err)
        return None

    async def get_user_repositories(self, session_id: str) -> List[Dict[str, Any]]:
        """Fetch and return only the authenticated user's repositories using their GitHub session token.
        Never returns default or shared user data.
        """
        session = await self.get_session(session_id)
        if not session or not session.get("access_token"):
            raise ValueError("Invalid or expired session. Please log in with GitHub.")

        token = session["access_token"]
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "Antigravity-Engine/1.0",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.github.com/user/repos?sort=updated&per_page=100&type=all",
                headers=headers,
            )

        if resp.status_code != 200:
            logger.error("GitHub API user repos failed: status %d %s", resp.status_code, resp.text)
            raise ValueError(f"Failed to fetch repositories from GitHub: {resp.status_code}")

        repos_raw = resp.json()
        formatted_repos = []

        for repo in repos_raw:
            formatted_repos.append(
                {
                    "id": repo.get("id"),
                    "name": repo.get("name"),
                    "full_name": repo.get("full_name"),
                    "owner": repo.get("owner", {}).get("login", ""),
                    "owner_avatar": repo.get("owner", {}).get("avatar_url", ""),
                    "html_url": repo.get("html_url"),
                    "default_branch": repo.get("default_branch", "main"),
                    "private": repo.get("private", False),
                    "description": repo.get("description") or "",
                    "updated_at": repo.get("updated_at"),
                    "stargazers_count": repo.get("stargazers_count", 0),
                    "forks_count": repo.get("forks_count", 0),
                }
            )

        return formatted_repos


# Global singleton instance
session_service = SessionService()
