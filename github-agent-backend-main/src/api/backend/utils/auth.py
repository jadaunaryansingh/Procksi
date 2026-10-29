"""
Authentication and authorization helpers for Supabase JWT tokens.
"""
from typing import Optional, Callable, Dict, Any
from fastapi import Header, HTTPException, status, Depends

from src.api.backend.database import get_supabase_client
from src.api.backend.crud import UserCRUD


class AuthContext(Dict[str, Any]):
    """Simple container for authenticated user context."""


async def get_current_user(
    authorization: Optional[str] = Header(None, convert_underscores=False)
) -> AuthContext:
    """
    Bypassed JWT verification for standalone deployment.
    Always returns a mock admin user context.
    Ensures mock admin profile exists in the users table.
    """
    mock_id = "00000000-0000-0000-0000-000000000000"
    try:
        profile = UserCRUD.get_or_create_user(mock_id, email="admin@standalone.local", full_name="Standalone Admin")
        # Ensure it has admin role and is_mentor set
        if profile.get("role") != "admin" or not profile.get("is_mentor"):
            from src.api.backend.database import get_supabase_admin_client
            get_supabase_admin_client().table("users").update({"role": "admin", "is_mentor": True}).eq("id", mock_id).execute()
            profile["role"] = "admin"
            profile["is_mentor"] = True
    except Exception as e:
        print(f"[Utils Auth] Failed to ensure mock admin in DB: {e}")
        profile = {"role": "admin", "is_mentor": True, "full_name": "Standalone Admin"}

    return AuthContext({
        "user_id": mock_id,
        "email": "admin@standalone.local",
        "role": "admin",
        "profile": profile
    })


def require_role(*allowed_roles: str) -> Callable[[AuthContext], AuthContext]:
    """
    Dependency factory to enforce role-based access on endpoints.
    Usage: Depends(require_role("admin", "mentor"))
    """

    async def dependency(ctx: AuthContext = Depends(get_current_user)) -> AuthContext:
        role = ctx.get("role")
        if role not in allowed_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return ctx

    return dependency
