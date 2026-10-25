import hmac

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.supabase_client import get_supabase_service
from app.security import decode_token

security = HTTPBearer(auto_error=False)


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> dict:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(creds.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    def _fetch_user():
        client = get_supabase_service()
        if client is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Supabase not configured")
        res = client.table("users").select("*").eq("email", payload["sub"]).execute()
        if not res.data:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return res.data[0]

    from app.cache import get_cached
    try:
        return get_cached(f"auth_user:{payload['sub']}", 30.0, _fetch_user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


def require_panel_access(panel_id: str, user: dict) -> None:
    role = user.get("role")
    p_id = user.get("panel_id")
    if role == "admin":
        return
    if role not in ("panel", "mentor"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Panel role required")
    if not p_id or p_id != panel_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Wrong panel for this user")


def require_admin_key(x_admin_api_key: Annotated[str | None, Header()] = None) -> None:
    """
    Dependency used on admin-sync endpoints.
    The admin portal must send `X-Admin-Api-Key: <ADMIN_API_KEY>` in the request.
    """
    if not x_admin_api_key or not hmac.compare_digest(x_admin_api_key, settings.admin_api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing X-Admin-Api-Key header",
        )
