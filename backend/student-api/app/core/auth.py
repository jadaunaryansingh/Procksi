"""
core/auth.py — Zero-trust authentication helpers.

Token strategy
--------------
Access token  : Short-lived (15 min by default). Contains only `sub` (admin UUID)
                and `jti` (a unique token ID). Role is NEVER encoded here.
Refresh token : Long-lived (7 days by default). A cryptographically random string.
                Only its SHA-256 hash is stored in the DB.

On every request
----------------
1. Decode access token → validate signature + expiry.
2. Look up the `jti` in `revoked_tokens` — reject if found (logged-out token).
3. Fetch the Admin row from DB using `sub` → get live role, confirm account exists.

On logout
---------
The token's `jti` is inserted into `revoked_tokens` so it cannot be reused
even if it hasn't expired yet. The refresh token record is deleted.
"""

import asyncio
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.database import get_db

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
# rounds=10 is the performance/security sweet spot for an admin portal:
# rounds=12 (default) → ~300ms  |  rounds=10 → ~75ms  |  rounds=8 → ~20ms (too weak)
# OWASP recommends 10+ for bcrypt. Do NOT go below 10.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=10)
bearer_scheme = HTTPBearer()


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# Access token  (short-lived, carries only sub + jti)
# ---------------------------------------------------------------------------

# `aud` scopes a token to this service. Until now mentor-api, panel-api and
# student-api all signed with the *same* SECRET_KEY and checked none of this,
# so a token minted by any one service passed verification on the other two —
# one leaked secret compromised three services at once with no boundary
# stopping cross-service replay (audit finding L-1). Each service now has its
# own secret (see .env) and only accepts tokens carrying its own audience.
_AUDIENCE = "student-api"


def create_access_token(admin_id: str, expires_delta: timedelta | None = None) -> tuple[str, str]:
    """
    Create a signed JWT access token.

    Returns
    -------
    (encoded_token, jti) — the caller needs the jti to blacklist on logout.
    """
    jti = str(uuid.uuid4())
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": admin_id, "jti": jti, "exp": expire, "aud": _AUDIENCE}
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, jti


def _decode_access_token(token: str) -> dict:
    """Decode and validate the JWT. Raises 401 on any failure."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM], audience=_AUDIENCE)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_UNAUTHORIZED", "message": "Invalid or expired token"},
        )


# ---------------------------------------------------------------------------
# Refresh token  (long-lived, stored as SHA-256 hash in DB)
# ---------------------------------------------------------------------------

def _hash_token(raw: str) -> str:
    """Return the SHA-256 hex digest of a raw token string."""
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_refresh_token() -> tuple[str, str]:
    """
    Generate a cryptographically secure refresh token.

    Returns
    -------
    (raw_token, hashed_token) — store the hash, return raw to the client.
    """
    raw = secrets.token_urlsafe(48)
    return raw, _hash_token(raw)


async def store_refresh_token(
    db: AsyncSession, admin_id: uuid.UUID, token_hash: str
) -> None:
    """Replace any existing refresh token for this admin with the new one.

    NOTE: This function does NOT commit. The caller is responsible for
    committing the session so that the DELETE + INSERT can be batched
    with any other work in the same transaction (single round-trip).
    """
    from app.models.refresh_token import RefreshToken

    # Remove old tokens for this admin — one active refresh token per admin
    await db.execute(
        delete(RefreshToken).where(RefreshToken.admin_id == admin_id)
    )
    expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    db.add(RefreshToken(admin_id=admin_id, token_hash=token_hash, expires_at=expires_at))


async def store_refresh_token_rest(admin_id: str, token_hash: str) -> None:
    """REST (HTTPS) equivalent of :func:`store_refresh_token`.

    Used by the login path so it works on networks that block direct Postgres
    ports. Replaces any existing refresh token for this admin.
    """
    import logging
    import uuid as _uuid

    from app.core import rest_db

    _log = logging.getLogger(__name__)

    now = datetime.utcnow()
    expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    try:
        await rest_db.delete("refresh_tokens", {"admin_id": admin_id})
        await rest_db.insert(
            "refresh_tokens",
            {
                "id": str(_uuid.uuid4()),
                "admin_id": admin_id,
                "token_hash": token_hash,
                "expires_at": expires_at.isoformat(),
                # created_at has a Python-side default on the ORM model, not a
                # DB default, so inserting over REST must supply it explicitly.
                "created_at": now.isoformat(),
            },
        )
    except Exception as exc:
        # The deployed Supabase `refresh_tokens` table is keyed by mentor_id and
        # has no admin_id column, so admin refresh tokens cannot be persisted
        # against it. Login must still succeed — the access token is valid; only
        # refresh-token rotation is unavailable until the schema is reconciled.
        _log.warning(
            "Refresh token not persisted for admin %s (schema mismatch): %s",
            admin_id, exc,
        )


async def verify_refresh_token(
    db: AsyncSession, raw_token: str
) -> "Admin":  # type: ignore[name-defined]
    """
    Validate a raw refresh token against its stored hash.

    Returns the Admin record if valid.  Raises 401 if not.
    """
    from app.models.refresh_token import RefreshToken
    from app.models.admin import Admin

    token_hash = _hash_token(raw_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    record = result.scalar_one_or_none()

    if not record or record.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_UNAUTHORIZED", "message": "Refresh token invalid or expired"},
        )

    result = await db.execute(select(Admin).where(Admin.id == record.admin_id))
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_UNAUTHORIZED", "message": "Account not found or deleted"},
        )
    return admin


async def revoke_refresh_token(db: AsyncSession, raw_token: str) -> None:
    """Delete the refresh token record so it can never be reused.
    
    NOTE: This function does NOT commit. Callers must commit the session.
    """
    from app.models.refresh_token import RefreshToken

    token_hash = _hash_token(raw_token)
    await db.execute(
        delete(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )


# ---------------------------------------------------------------------------
# Token blacklist  (for logout-before-expiry)
# ---------------------------------------------------------------------------

async def blacklist_jti(
    db: AsyncSession, jti: str, expires_at: datetime
) -> None:
    """Insert a JTI into the revoked_tokens table.
    
    NOTE: This function does NOT commit. Callers must commit the session.
    """
    from app.models.revoked_token import RevokedToken

    db.add(RevokedToken(jti=jti, revoked_at=datetime.utcnow(), expires_at=expires_at))


async def _is_jti_revoked(db: AsyncSession, jti: str) -> bool:
    from app.models.revoked_token import RevokedToken

    result = await db.execute(
        select(RevokedToken).where(RevokedToken.jti == jti)
    )
    return result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# FastAPI dependency — plugged into every protected route
# ---------------------------------------------------------------------------

async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """
    Zero-trust request guard.

    1. Decode token — validates signature and expiry.
    2. Extract jti — check it hasn't been revoked (logout blacklist).
    3. Extract sub — fetch live Admin from DB (role, existence verified each request).
    """
    from app.models.admin import Admin

    payload = _decode_access_token(credentials.credentials)

    jti: str | None = payload.get("jti")
    admin_id: str | None = payload.get("sub")

    if not jti or not admin_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_UNAUTHORIZED", "message": "Token payload invalid"},
        )

    # UUID cast — catch malformed payloads
    try:
        admin_uuid = uuid.UUID(admin_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_UNAUTHORIZED", "message": "Token payload invalid"},
        )

    # Live DB lookup + Blacklist check combined into a single database round-trip
    from app.models.revoked_token import RevokedToken
    query = (
        select(Admin)
        .where(Admin.id == admin_uuid)
        .where(
            ~select(RevokedToken)
            .where(RevokedToken.jti == jti)
            .exists()
        )
    )
    # DB can be flaky on local networks (WARP/VPN). Retry once and surface a clear 503.
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            result = await db.execute(query)
            admin = result.scalar_one_or_none()
            break
        except (asyncio.TimeoutError, OSError, SQLAlchemyError) as e:
            last_err = e
            # brief backoff before retrying
            if attempt == 0:
                await asyncio.sleep(0.25)
                continue
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "DB_UNAVAILABLE",
                    "message": "Database temporarily unavailable. Please retry.",
                },
            ) from e
    
    if not admin:
        # If admin evaluates to None here, it means either:
        # 1. The account was deleted.
        # 2. The token JTI was found in the revoked_tokens blacklist.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_UNAUTHORIZED", "message": "Account deleted or token revoked"},
        )

    # Attach jti to admin object so the logout route can blacklist it without
    # re-decoding the token
    admin._jti = jti
    admin._token_exp = datetime.utcfromtimestamp(payload["exp"])
    return admin


async def get_super_admin(admin=Depends(get_current_admin)):
    """Role gate — requires SUPER_ADMIN. Role is always from DB, not from token."""
    if admin.role != "SUPER_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "AUTH_FORBIDDEN", "message": "SUPER_ADMIN role required"},
        )
    return admin
