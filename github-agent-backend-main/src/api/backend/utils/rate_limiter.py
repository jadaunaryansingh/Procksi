"""
Rate Limiter Utility
Redis-backed rate limiting using SlowAPI for FastAPI endpoints.
"""
import os
import logging
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("rate_limiter")


def _get_rate_limit_key(request: Request) -> str:
    """
    Custom key function for rate limiting.
    Uses authenticated user ID when available, falls back to client IP.
    """
    # Try to extract user ID from the auth state (set by auth middleware)
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        try:
            # Decode JWT to extract user ID (sub claim) without full verification
            # SlowAPI just needs a stable identifier, not cryptographic verification
            import jwt as pyjwt
            payload = pyjwt.decode(token, options={"verify_signature": False})
            user_id = payload.get("sub")
            if user_id:
                return f"user:{user_id}"
        except Exception:
            pass

    # Fallback to IP address
    return get_remote_address(request)


def _custom_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return a proper JSON 429 response with Retry-After header."""
    retry_after = getattr(exc, "retry_after", 60)
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please slow down.",
            "retry_after": retry_after
        },
        headers={"Retry-After": str(retry_after)}
    )


def _get_storage_uri() -> str:
    """Get the Redis URL for rate limit storage, or fallback to memory."""
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        return redis_url
    return "memory://"


# --- Global Limiter Instance ---
limiter = Limiter(
    key_func=_get_rate_limit_key,
    default_limits=["60/minute"],
    storage_uri=_get_storage_uri(),
    strategy="fixed-window",
)

# Re-export for convenience
__all__ = [
    "limiter",
    "SlowAPIMiddleware",
    "RateLimitExceeded",
    "_custom_rate_limit_exceeded_handler",
]
