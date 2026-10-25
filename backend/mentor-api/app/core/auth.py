"""
core/auth.py — Zero-trust authentication helpers.

Token strategy
--------------
Access token  : Short-lived (15 min by default). Contains only `sub` (mentor string ID)
                and `jti` (a unique token ID). Role is NEVER encoded here.
Refresh token : Long-lived (7 days by default). A cryptographically random string.
                Only its SHA-256 hash is stored in the DB.

On every request
----------------
1. Decode access token → validate signature + expiry.
2. Look up the `jti` in `revoked_tokens` — reject if found (logged-out token).
3. Fetch the Mentor row from DB using `sub` → verify existence and check is_active.

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
import bcrypt
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.database import get_db

bearer_scheme = HTTPBearer()


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# `aud` scopes a token to this service. Until now mentor-api, panel-api and
# student-api all signed with the *same* SECRET_KEY and checked none of this,
# so a token minted by any one service passed verification on the other two —
# one leaked secret compromised three services at once with no boundary
# stopping cross-service replay (audit finding L-1). Each service now has its
# own secret (see .env) and only accepts tokens carrying its own audience.
_AUDIENCE = "mentor-api"


# Access token (short-lived, carries only sub + jti)
def create_access_token(mentor_id: str, expires_delta: timedelta | None = None) -> tuple[str, str]:
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
    payload = {"sub": mentor_id, "jti": jti, "exp": expire, "aud": _AUDIENCE}
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


# Refresh token (long-lived, stored as SHA-256 hash in DB)
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
    db: AsyncSession, mentor_id: str, token_hash: str
) -> None:
    """Replace any existing refresh token for this mentor with the new one.

    NOTE: This function does NOT commit. The caller is responsible for committing.
    """
    from app.models.refresh_token import RefreshToken

    # Remove old tokens for this mentor
    await db.execute(
        delete(RefreshToken).where(RefreshToken.mentor_id == mentor_id)
    )
    expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    db.add(RefreshToken(mentor_id=mentor_id, token_hash=token_hash, expires_at=expires_at))


async def store_refresh_token_rest(mentor_id: str, token_hash: str) -> None:
    """REST (HTTPS) equivalent of :func:`store_refresh_token`.

    Used by the login path so it works on networks that block direct Postgres
    ports. Replaces any existing refresh token for this mentor.
    """
    import uuid as _uuid

    from app.core import rest_db

    await rest_db.delete("refresh_tokens", {"mentor_id": mentor_id})
    now = datetime.utcnow()
    expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    await rest_db.insert(
        "refresh_tokens",
        {
            "id": str(_uuid.uuid4()),
            "mentor_id": mentor_id,
            "token_hash": token_hash,
            "expires_at": expires_at.isoformat(),
            # created_at has a Python-side default on the ORM model, not a DB
            # default, so inserting over REST must supply it explicitly.
            "created_at": now.isoformat(),
        },
    )


async def verify_refresh_token(
    db: AsyncSession, raw_token: str
) -> "Mentor":  # type: ignore[name-defined]
    """
    Validate a raw refresh token against its stored hash.

    Returns the Mentor record if valid. Raises 401 if not.
    """
    from app.models.refresh_token import RefreshToken
    from app.models.mentor import Mentor

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

    result = await db.execute(select(Mentor).where(Mentor.id == record.mentor_id))
    mentor = result.scalar_one_or_none()
    if not mentor:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_UNAUTHORIZED", "message": "Account not found or deleted"},
        )
    return mentor


async def revoke_refresh_token(db: AsyncSession, raw_token: str) -> None:
    """Delete the refresh token record so it can never be reused.
    
    NOTE: This function does NOT commit.
    """
    from app.models.refresh_token import RefreshToken

    token_hash = _hash_token(raw_token)
    await db.execute(
        delete(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )


# Token blacklist (for logout-before-expiry)
async def blacklist_jti(
    db: AsyncSession, jti: str, expires_at: datetime
) -> None:
    """Insert a JTI into the revoked_tokens table.
    
    NOTE: This function does NOT commit.
    """
    from app.models.revoked_token import RevokedToken

    db.add(RevokedToken(jti=jti, revoked_at=datetime.utcnow(), expires_at=expires_at))


async def _is_jti_revoked(db: AsyncSession, jti: str) -> bool:
    from app.models.revoked_token import RevokedToken

    result = await db.execute(
        select(RevokedToken).where(RevokedToken.jti == jti)
    )
    return result.scalar_one_or_none() is not None


# FastAPI dependency — plugged into protected routes
async def get_current_mentor(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """
    Zero-trust request guard.

    1. Decode token — validates signature and expiry.
    2. Extract jti — check it hasn't been revoked.
    3. Extract sub — fetch live Mentor from DB and check is_active.
    """
    from app.models.mentor import Mentor

    payload = _decode_access_token(credentials.credentials)

    jti: str | None = payload.get("jti")
    mentor_id: str | None = payload.get("sub")

    if not jti or not mentor_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_UNAUTHORIZED", "message": "Token payload invalid"},
        )

    cache_key = f"auth_mentor:{mentor_id}:{jti}"
    from app.core.cache import peek, set_value
    hit, cached_mentor = peek(cache_key, 30.0)
    if hit and cached_mentor is not None:
        return cached_mentor

    # Live DB lookup + Blacklist check combined into a single database round-trip
    from app.models.revoked_token import RevokedToken
    query = (
        select(Mentor)
        .where(Mentor.id == mentor_id)
        .where(
            ~select(RevokedToken)
            .where(RevokedToken.jti == jti)
            .exists()
        )
    )

    mentor = None
    last_err: Exception | None = None

    # Try HTTPS REST lookup first if configured for fast zero-hang auth.
    #
    # `query` above pairs the mentor lookup with a NOT EXISTS check against
    # revoked_tokens. This path bypasses that query, so it must check the
    # blacklist itself — otherwise logout reports success while the access token
    # keeps working until it expires, and an administrator cannot force-revoke a
    # compromised session at all.
    try:
        from app.core import rest_db
        if rest_db.is_configured():
            revoked = await rest_db.select_one("revoked_tokens", eq={"jti": jti})
            if revoked:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"code": "AUTH_UNAUTHORIZED", "message": "Account deleted or token revoked"},
                )
            raw_m = await rest_db.select_one("mentors", eq={"id": mentor_id})
            if raw_m:
                mentor = Mentor(
                    id=raw_m.get("id"),
                    name=raw_m.get("name") or "",
                    email=raw_m.get("email") or "",
                    expertise=raw_m.get("expertise") or "",
                    domains=raw_m.get("domains") or [],
                    is_active=bool(raw_m.get("is_active", True))
                )
    except HTTPException:
        # A revoked token must propagate, not be swallowed as a REST failure and
        # silently retried against the database path.
        raise
    except Exception as rest_e:
        pass

    if not mentor:
        try:
            result = await asyncio.wait_for(db.execute(query), timeout=2.0)
            mentor = result.scalar_one_or_none()
        except Exception as e:
            last_err = e

    if not mentor and last_err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DB_UNAVAILABLE",
                "message": "Database temporarily unavailable. Please retry.",
            },
        )

    if not mentor:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_UNAUTHORIZED", "message": "Account deleted or token revoked"},
        )

    # Check approval status
    if not mentor.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "AUTH_PENDING_APPROVAL",
                "message": "Your registration is pending administrator approval. You can log in once approved."
            },
        )

    # Attach metadata for logout routing
    mentor._jti = jti
    mentor._token_exp = datetime.utcfromtimestamp(payload["exp"])
    set_value(cache_key, mentor)
    return mentor

async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Admin guard for the /api/admin/* routers mounted in this service.

    This used to be `get_current_admin = get_current_mentor`, so every admin-only
    route in this service accepted any approved mentor's token: a mentor could
    override results, set deadlines, freeze data and read audit logs. The identity
    is now resolved against the `admins` table, which no mentor is a row in, and
    the role is read from the database rather than from the token.
    """
    from app.models.admin import Admin
    from app.models.revoked_token import RevokedToken

    payload = _decode_access_token(credentials.credentials)

    jti: str | None = payload.get("jti")
    subject: str | None = payload.get("sub")
    if not jti or not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_UNAUTHORIZED", "message": "Token payload invalid"},
        )

    query = (
        select(Admin)
        .where(Admin.id == subject)
        .where(~select(RevokedToken).where(RevokedToken.jti == jti).exists())
    )

    try:
        result = await db.execute(query)
        admin = result.scalar_one_or_none()
    except Exception:
        # Fail closed: an unavailable database must not grant admin access.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "DB_UNAVAILABLE", "message": "Database temporarily unavailable. Please retry."},
        )

    if not admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "AUTH_FORBIDDEN", "message": "Administrator access required"},
        )

    admin._jti = jti
    admin._token_exp = datetime.utcfromtimestamp(payload["exp"])
    return admin


async def get_super_admin(admin=Depends(get_current_admin)):
    """Role gate — requires SUPER_ADMIN. Role is always from the DB, not the token."""
    if admin.role != "SUPER_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "AUTH_FORBIDDEN", "message": "SUPER_ADMIN role required"},
        )
    return admin
