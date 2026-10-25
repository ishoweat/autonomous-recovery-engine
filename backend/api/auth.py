from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
import httpx
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.services.session_service import session_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/github", tags=["Auth"])
v1_auth_router = APIRouter(prefix="/api/v1/auth", tags=["Auth V1"])


class TokenLoginRequest(BaseModel):
    token: str = Field(..., description="GitHub Personal Access Token or OAuth Access Token")
    ttl: Optional[int] = Field(default=3600, description="Session TTL in seconds (default: 3600)")


async def get_session_id_from_request(
    session_id_cookie: Optional[str] = Cookie(None, alias="session_id"),
    github_token_cookie: Optional[str] = Cookie(None, alias="github_token"),
    authorization: Optional[str] = Header(None),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    query_session_id: Optional[str] = Query(None, alias="session_id"),
) -> Optional[str]:
    """Extract session ID or legacy token from request header, cookie, or query parameter."""
    if query_session_id and query_session_id.startswith("sess_"):
        return query_session_id
    if x_session_id:
        return x_session_id
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
        if authorization.startswith("sess_"):
            return authorization
    if session_id_cookie:
        return session_id_cookie
    return github_token_cookie


async def get_current_session(
    session_id: Optional[str] = Depends(get_session_id_from_request),
) -> Optional[Dict[str, Any]]:
    """FastAPI dependency to retrieve active Redis session."""
    if not session_id:
        return None

    # If the session_id is a raw token, check if it starts with 'sess_' or try session retrieval
    if session_id.startswith("sess_"):
        session = await session_service.get_session(session_id)
        if session:
            return session

    # Fallback for legacy raw token cookies: validate token with GitHub and create temporary session
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {session_id}",
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "Antigravity-Engine/1.0",
                },
            )
            if resp.status_code == 200:
                user_info = resp.json()
                return await session_service.create_session(user_info, session_id)
    except Exception:
        pass

    return None


async def require_active_session(
    session: Optional[Dict[str, Any]] = Depends(get_current_session),
) -> Dict[str, Any]:
    """FastAPI dependency requiring an active, unexpired Redis session."""
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Active GitHub session required or session expired. Please log in with GitHub.",
        )
    return session


@router.get("/status")
@v1_auth_router.get("/status")
async def github_status():
    settings = get_settings()
    return {
        "configured": bool(settings.github_client_id and settings.github_client_secret),
        "session_ttl_default": session_service.default_ttl,
    }


@router.get("/login")
@v1_auth_router.get("/login")
async def github_login():
    settings = get_settings()
    if not settings.github_client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub Client ID not configured.",
        )

    github_auth_url = (
        f"https://github.com/login/oauth/authorize?"
        f"client_id={settings.github_client_id}&"
        f"scope=repo%20user&"
        f"redirect_uri={settings.github_redirect_uri}"
    )
    return RedirectResponse(url=github_auth_url)


@router.get("/callback")
@v1_auth_router.get("/callback")
async def github_callback(code: str = Query(...)):
    settings = get_settings()
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub credentials not configured.",
        )

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_redirect_uri,
            },
        )

    if token_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to authenticate with GitHub")

    data = token_resp.json()
    access_token = data.get("access_token")
    if not access_token:
        error_msg = data.get("error_description", str(data))
        raise HTTPException(status_code=400, detail=f"No access token received from GitHub: {error_msg}")

    # Fetch GitHub user profile for session creation
    async with httpx.AsyncClient(timeout=10.0) as client:
        user_resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Antigravity-Engine/1.0",
            },
        )

    if user_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch GitHub user profile.")

    user_info = user_resp.json()

    # Create unique Redis session for user
    session = await session_service.create_session(user_info, access_token)
    session_id = session["session_id"]

    # Redirect to cookie helper with session_id only (never expose raw OAuth token in URL)
    redirect_url = f"/auth/github/set-cookie?session_id={session_id}"
    return RedirectResponse(url=redirect_url)


@router.get("/set-cookie")
@v1_auth_router.get("/set-cookie")
async def github_set_cookie(
    session_id: str = Query(...),
    token: Optional[str] = Query(None),
):
    settings = get_settings()
    frontend_url = f"{settings.frontend_url}/detect?session_id={session_id}"
    response = RedirectResponse(url=frontend_url)

    is_prod = settings.environment == "production"
    cookie_samesite = "none" if is_prod else "lax"
    cookie_secure = True if is_prod else (settings.environment != "development")

    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=session_service.default_ttl,
    )

    # Securely retrieve user access token from server-side session without relying on URL params
    resolved_token = token
    if not resolved_token:
        sess = await session_service.get_session(session_id)
        if sess and sess.get("access_token"):
            resolved_token = sess["access_token"]

    if resolved_token:
        response.set_cookie(
            key="github_token",
            value=resolved_token,
            httponly=True,
            secure=cookie_secure,
            samesite=cookie_samesite,
            max_age=session_service.default_ttl,
        )
    return response


@router.post("/token-login")
@v1_auth_router.post("/token-login")
async def token_login(payload: TokenLoginRequest, response: Response):
    """Create a Redis GitHub session directly using a Personal Access Token or OAuth Token."""
    token = payload.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token is required.")

    async with httpx.AsyncClient(timeout=10.0) as client:
        user_resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Antigravity-Engine/1.0",
            },
        )

    if user_resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid GitHub token or failed to verify identity with GitHub API.",
        )

    user_info = user_resp.json()
    ttl = payload.ttl or session_service.default_ttl

    session = await session_service.create_session(user_info, token, ttl=ttl)

    settings = get_settings()
    is_prod = settings.environment == "production"
    cookie_samesite = "none" if is_prod else "lax"
    cookie_secure = True if is_prod else (settings.environment != "development")

    response.set_cookie(
        key="session_id",
        value=session["session_id"],
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=ttl,
    )
    response.set_cookie(
        key="github_token",
        value=token,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=ttl,
    )

    return {
        "authenticated": True,
        "session": {
            "session_id": session["session_id"],
            "user_id": session["user_id"],
            "username": session["username"],
            "display_name": session["display_name"],
            "avatar_url": session["avatar_url"],
            "expires_at": session["expires_at"],
            "ttl_remaining": session["ttl"],
        },
    }


@router.get("/me")
@v1_auth_router.get("/me")
async def get_current_user_profile(
    session: Optional[Dict[str, Any]] = Depends(get_current_session),
):
    """Get profile and TTL info of the currently logged-in GitHub user session."""
    if not session:
        return {
            "authenticated": False,
            "message": "No active session found.",
        }

    return {
        "authenticated": True,
        "session": {
            "session_id": session["session_id"],
            "user_id": session["user_id"],
            "username": session["username"],
            "display_name": session["display_name"],
            "avatar_url": session["avatar_url"],
            "created_at": session.get("created_at"),
            "expires_at": session.get("expires_at"),
            "ttl_remaining": session.get("ttl_remaining", session.get("ttl", 3600)),
        },
    }


@router.post("/logout")
@v1_auth_router.post("/logout")
@router.get("/logout")
@v1_auth_router.get("/logout")
async def logout(
    response: Response,
    session_id: Optional[str] = Depends(get_session_id_from_request),
):
    """Immediately destroy session in Redis and clear authentication cookies."""
    deleted = False
    if session_id:
        deleted = await session_service.delete_session(session_id)

    response.delete_cookie("session_id")
    response.delete_cookie("github_token")

    return {
        "success": True,
        "session_deleted": deleted,
        "message": "Session invalidated and deleted from Redis successfully.",
    }
