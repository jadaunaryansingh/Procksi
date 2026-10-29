"""
Role Manager - Smart role detection and assignment for new users
"""
import os
from typing import Optional


class RoleManager:
    """
    Intelligent role assignment for new users based on multiple criteria:
    1. Supabase Auth metadata (app_metadata or user_metadata)
    2. First user privilege (first user becomes admin)
    3. Admin email whitelist (environment variable)
    4. Default to 'mentor'
    
    Note: Domain-based auto-admin removed to prevent accidentally making
    all college/university users admins when mentors also use those domains.
    """
    
    # Cache for admin emails from environment
    _admin_emails_cache: Optional[set] = None
    
    @classmethod
    def _get_admin_emails(cls) -> set:
        """Get admin emails from environment variable"""
        if cls._admin_emails_cache is None:
            admin_emails_str = os.getenv("ADMIN_EMAILS", "")
            cls._admin_emails_cache = {
                email.strip().lower() 
                for email in admin_emails_str.split(",") 
                if email.strip()
            }
        return cls._admin_emails_cache
    
    @classmethod
    def determine_role(
        cls,
        email: Optional[str],
        auth_metadata: Optional[dict] = None,
        is_first_user: bool = False
    ) -> str:
        """
        Determine the appropriate role for a new user.
        
        Priority order:
        1. Auth metadata (app_metadata.role or user_metadata.role)
        2. First user privilege (becomes admin)
        3. Admin email whitelist
        4. Default to 'mentor'
        
        Args:
            email: User's email address
            auth_metadata: Combined app_metadata and user_metadata from Supabase Auth
            is_first_user: Whether this is the first user in the system
            
        Returns:
            Role string: "admin" or "mentor"
        """
        
        # Priority 1: Check auth metadata
        if auth_metadata:
            metadata_role = auth_metadata.get("role")
            if metadata_role in ["admin", "mentor"]:
                print(f"[RoleManager] Role from auth metadata: {metadata_role}")
                return metadata_role
        
        # Priority 2: First user privilege
        if is_first_user:
            print(f"[RoleManager] First user detected - assigning admin role")
            return "admin"
        
        # Priority 3: Check admin email whitelist
        if email:
            email_lower = email.lower()
            admin_emails = cls._get_admin_emails()
            
            if email_lower in admin_emails:
                print(f"[RoleManager] Email in admin whitelist: {email}")
                return "admin"
        
        # Default: Mentor role
        print(f"[RoleManager] No admin criteria met - defaulting to mentor role")
        return "mentor"
    
    @classmethod
    def is_valid_role(cls, role: Optional[str]) -> bool:
        """Check if a role is valid"""
        return role in ["admin", "mentor"]
    
    @classmethod
    def normalize_role(cls, role: Optional[str]) -> str:
        """Normalize and validate role, return default if invalid"""
        if cls.is_valid_role(role):
            return role
        return "mentor"
