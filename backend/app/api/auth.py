import os
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_admin
from app.core.auth import (
    verify_password,
    create_access_token,
    generate_refresh_token,
    store_refresh_token,
    verify_refresh_token,
    revoke_refresh_token,
    blacklist_jti,
)
from app.models.admin import Admin
from app.schemas.auth import AdminLogin, TokenResponse, RefreshRequest
from app.schemas.common import ok


def _allowed_email_suffix() -> str:
    """'@' + ALLOWED_EMAIL_DOMAIN. Unset rejects every address (fail closed)."""
    return "@" + os.getenv("ALLOWED_EMAIL_DOMAIN", "").strip().lstrip("@").lower()


def _master_admin_email() -> str:
    return os.getenv("MASTER_ADMIN_EMAIL", "").strip().lower()


router = APIRouter(prefix="/api/admin", tags=["Auth"])


@router.post("/login")
async def admin_login(payload: AdminLogin, db: AsyncSession = Depends(get_db)):
    """
    Authenticate an admin and return a short-lived access token + long-lived refresh token.
    """
    email_clean = payload.email.strip().lower()
    if not email_clean.endswith(_allowed_email_suffix()) and email_clean != _master_admin_email():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": {
                    "code": "AUTH_FORBIDDEN",
                    "message": f"Only {_allowed_email_suffix()} email addresses are permitted.",
                },
            },
        )
    result = await db.execute(select(Admin).where(Admin.email == payload.email))
    admin = result.scalar_one_or_none()

    if not admin or not verify_password(payload.password, admin.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "error": {
                    "code": "AUTH_INVALID_CREDENTIALS",
                    "message": "Invalid email or password",
                },
            },
        )

    # Issue tokens — role stays in DB, not in the token
    access_token, _jti = create_access_token(str(admin.id))
    raw_refresh, hashed_refresh = generate_refresh_token()

    # Batch the DELETE + INSERT into a single commit (one DB round-trip)
    await store_refresh_token(db, admin.id, hashed_refresh)
    await db.commit()

    return ok(
        data=TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            token_type="bearer",
            role=admin.role,   # for UI display only — backend never trusts this
            name=admin.name,
        ).model_dump(),
        message="Login successful",
    )


@router.post("/refresh")
async def refresh_access_token(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """
    Exchange a valid refresh token for a new access token.
    Issues a new refresh token as well (token rotation — old one is invalidated).
    """
    admin = await verify_refresh_token(db, payload.refresh_token)

    # Rotate: delete old refresh token, issue a new one
    await revoke_refresh_token(db, payload.refresh_token)
    new_access, _jti = create_access_token(str(admin.id))
    new_raw_refresh, new_hashed_refresh = generate_refresh_token()
    await store_refresh_token(db, admin.id, new_hashed_refresh)
    await db.commit()

    return ok(
        data=TokenResponse(
            access_token=new_access,
            refresh_token=new_raw_refresh,
            token_type="bearer",
            role=admin.role,
            name=admin.name,
        ).model_dump(),
        message="Token refreshed",
    )


@router.post("/logout")
async def logout(admin=Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    """
    Invalidate the current access token (via JTI blacklist) and delete the refresh token.
    After this call, neither token can be used.
    """
    from sqlalchemy import delete
    from app.models.refresh_token import RefreshToken

    # Blacklist current access token's JTI until its natural expiry
    await blacklist_jti(db, admin._jti, admin._token_exp)

    # Delete all active refresh tokens for this admin
    await db.execute(delete(RefreshToken).where(RefreshToken.admin_id == admin.id))
    await db.commit()

    return ok(message="Logged out successfully")
