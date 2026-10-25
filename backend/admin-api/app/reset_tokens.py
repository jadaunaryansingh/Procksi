"""Signing and single-use tracking for admin password-reset tokens.

These tokens used to be signed with `SUPABASE_SERVICE_ROLE_KEY`, falling back to a
literal baked into the source. Reusing an API key as HMAC key material means a
leak of either one compromises both, and the fallback meant a deployment missing
that variable signed with a value published in the repository — anyone could mint
a reset token for the coordinator account. There was also no replay protection, so
a token stayed usable for its whole validity window.

The secret is now dedicated and required, and every token carries a jti that is
burned on first successful use.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Any

import jwt
from fastapi import HTTPException, status

ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 15 * 60

_used_jtis: dict[str, float] = {}
_lock = threading.Lock()


def _secret() -> str:
    """The dedicated reset-signing secret. Never falls back to another key."""
    secret = (os.getenv("PASSWORD_RESET_SECRET") or "").strip()
    if not secret:
        # Fail closed and loudly: a reset flow that signs with a guessable or
        # shared key is worse than one that is temporarily unavailable.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password reset is not configured. Set PASSWORD_RESET_SECRET.",
        )
    return secret


def _burn_expired(now: float) -> None:
    for jti, expires_at in list(_used_jtis.items()):
        if expires_at < now:
            _used_jtis.pop(jti, None)


def issue(email: str, portal: str = "admin") -> str:
    now = int(time.time())
    payload = {
        "email": email.strip().lower(),
        "portal": portal,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def consume(token: str) -> dict[str, Any]:
    """Verify a reset token and burn its jti. Raises on invalid or replayed tokens."""
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="This reset link has expired. Please request a new one.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="This reset link is invalid. Please request a new one.")

    jti = payload.get("jti")
    if not jti:
        raise HTTPException(status_code=400, detail="This reset link is invalid. Please request a new one.")

    now = time.time()
    with _lock:
        _burn_expired(now)
        if jti in _used_jtis:
            raise HTTPException(
                status_code=400,
                detail="This reset link has already been used. Please request a new one.",
            )
        _used_jtis[jti] = float(payload.get("exp") or (now + TOKEN_TTL_SECONDS))

    return payload
