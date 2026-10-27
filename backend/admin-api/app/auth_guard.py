"""Authentication for the admin API.

Every route in this service reads and writes through a Supabase *service role*
client, which bypasses row level security entirely. Until this module existed the
service had no authentication of any kind: no route dependency, no auth
middleware, and the only middleware present checked a semester freeze flag rather
than identity. Anything reachable at /api/ was therefore world readable and world
writable, including the student and mentor tables and the admin account
management endpoints.

`require_admin` is registered once as an application level dependency so that new
routes are covered by default — the previous state was a single forgotten
`Depends` away from recurring. Tokens are validated against Supabase's own user
endpoint, the same way student-api and mentor-api validate theirs.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Paths served without a session. Everything else requires an admin token.
# Kept exact-match rather than prefix-match so that a future /api/auth/<anything>
# route is closed by default instead of silently inheriting an exemption.
PUBLIC_PATHS = frozenset(
    {
        "/",
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/auth/login",
        # Public by necessity: it exists to replace an access token that has
        # already expired, so requiring a valid one would defeat it. The
        # refresh token in the body is itself the credential, and Supabase
        # rejects any that is expired, rotated, or revoked.
        "/api/auth/refresh",
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
        "/auth/google/callback",
        "/api/events/google-auth-callback",
    }
)

_bearer = HTTPBearer(auto_error=False)

# Validated identities, keyed by token. Supabase is the authority; this only
# avoids a round trip per request within a short window. Entries are pruned on
# write so the map cannot grow without bound.
_IDENTITY_TTL_SECONDS = 30.0
_MAX_CACHED_IDENTITIES = 512
_identity_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _master_admin_email() -> str:
    return os.getenv("MASTER_ADMIN_EMAIL", "").strip().lower()


def _cache_get(token: str) -> dict[str, Any] | None:
    entry = _identity_cache.get(token)
    if not entry:
        return None
    expires_at, identity = entry
    if expires_at < time.monotonic():
        _identity_cache.pop(token, None)
        return None
    return identity


def _cache_put(token: str, identity: dict[str, Any]) -> None:
    now = time.monotonic()
    if len(_identity_cache) >= _MAX_CACHED_IDENTITIES:
        for stale_token, (expires_at, _) in list(_identity_cache.items()):
            if expires_at < now:
                _identity_cache.pop(stale_token, None)
        if len(_identity_cache) >= _MAX_CACHED_IDENTITIES:
            _identity_cache.clear()
    _identity_cache[token] = (now + _IDENTITY_TTL_SECONDS, identity)


def invalidate_identity(token: str | None) -> None:
    """Drop a cached identity, so logout takes effect immediately."""
    if token:
        _identity_cache.pop(token, None)


async def _identity_from_token(token: str) -> dict[str, Any]:
    supabase_url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_PUBLISHABLE_KEY") or ""
    if not supabase_url or not supabase_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth is not configured on the server.",
        )

    cached = _cache_get(token)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{supabase_url}/auth/v1/user",
                headers={"Authorization": f"Bearer {token}", "apikey": supabase_key},
            )
    except Exception as exc:  # network/timeout — do not fall open
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service unavailable. Please retry.",
        ) from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session.",
        )

    user = response.json() or {}
    email = str(user.get("email") or "").strip().lower()
    # The role claim MUST come from app_metadata: it is writable only with the
    # service role key. user_metadata is attacker-controlled (POST /auth/v1/signup
    # `data:{...}`) — trusting it here let a self-registered account
    # (an attacker-chosen throwaway address, incident 2026-09-03) pass as an administrator.
    app_metadata = user.get("app_metadata") or {}
    role = str(app_metadata.get("role") or "").strip().lower()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session.",
        )

    if user.get("banned_until"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is disabled.",
        )

    is_master = email == _master_admin_email()
    if role != "admin" and not is_master:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )

    identity = {
        "id": user.get("id"),
        "email": email,
        "role": "admin",
        "is_master": is_master,
        "token": token,
    }
    _cache_put(token, identity)
    return identity


async def require_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any] | None:
    """Application level guard. Rejects anything without a valid admin session."""
    # CORS preflight carries no credentials by design.
    if request.method == "OPTIONS":
        return None
    if request.url.path.rstrip("/") in PUBLIC_PATHS or request.url.path in PUBLIC_PATHS:
        return None

    if credentials is None or (credentials.scheme or "").lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    identity = await _identity_from_token(credentials.credentials)
    request.state.admin = identity
    return identity


async def require_super_admin(request: Request) -> dict[str, Any]:
    """Guard for admin account management.

    Creating and deleting administrators is reserved for the master coordinator
    account: any other admin could otherwise mint peers or remove the owner.
    Depends on `require_admin` having already populated request.state.
    """
    identity = getattr(request.state, "admin", None)
    if not identity:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not identity.get("is_master"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the master coordinator account can manage administrators.",
        )
    return identity
