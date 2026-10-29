"""
CSRF Protection Configuration
Provides Cross-Site Request Forgery protection for state-changing operations
"""
import os
from fastapi_csrf_protect import CsrfProtect
from pydantic import BaseModel


class CsrfSettings(BaseModel):
    """CSRF Protection Settings"""
    secret_key: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    cookie_secure: bool = os.getenv("ENVIRONMENT") == "production"
    cookie_samesite: str = "lax"
    cookie_httponly: bool = True


@CsrfProtect.load_config
def get_csrf_config():
    """Load CSRF configuration"""
    return CsrfSettings()


def validate_csrf_token(csrf_protect: CsrfProtect, csrf_token: str = None):
    """
    Validate CSRF token for state-changing operations
    
    Args:
        csrf_protect: CSRF protection instance
        csrf_token: Token from request header or form
    
    Raises:
        CsrfProtectError: If token is invalid
    """
    csrf_protect.validate_csrf(csrf_token)
