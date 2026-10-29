"""
Admin User Management Router
Endpoints for managing user roles and permissions.
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from ..middleware.auth import get_current_user, AuthUser
from ..database import get_supabase_admin_client

router = APIRouter(prefix="/api/admin", tags=["admin-users"])


# Schemas
class UserResponse(BaseModel):
    id: str
    email: str
    role: Optional[str] = None  # "admin" | "mentor" | null
    is_mentor: Optional[bool] = None
    created_at: str
    last_sign_in_at: Optional[str] = None
    full_name: Optional[str] = None


class UserListResponse(BaseModel):
    users: List[UserResponse]


class UpdateRoleRequest(BaseModel):
    role: Optional[str]  # "admin" | "mentor" | null
    is_mentor: Optional[bool] = None


class UpdateRoleResponse(BaseModel):
    id: str
    email: str
    role: Optional[str]
    created_at: str
    updated_at: str
    message: str


@router.get("/users", response_model=UserListResponse)
async def list_users(current_user: AuthUser = Depends(get_current_user)):
    """
    List all users with their roles.
    Admin only.
    
    Returns:
        users: Array of user objects with id, email, role, timestamps
    """
    # Verify admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase_admin_client()
    
    try:
        # Query users table
        response = supabase.table("users").select(
            "id, email, role, is_mentor, created_at, last_sign_in_at, full_name"
        ).order("created_at", desc=True).execute()
        
        users = []
        for user in response.data:
            users.append({
                "id": user["id"],
                "email": user["email"],
                "role": user.get("role"),
                "is_mentor": user.get("is_mentor"),
                "created_at": user["created_at"],
                "last_sign_in_at": user.get("last_sign_in_at"),
                "full_name": user.get("full_name")
            })
        
        return {"users": users}
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to fetch users: {str(e)}"
        )


@router.patch("/users/{user_id}/role", response_model=UpdateRoleResponse)
async def update_user_role(
    user_id: str,
    request: UpdateRoleRequest,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Update user role (admin/mentor/null).
    Admin only.
    
    Args:
        user_id: UUID of user to update
        request: Object containing new role
        
    Returns:
        Updated user object with confirmation message
    """
    # Verify admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    new_role = request.role
    new_is_mentor = request.is_mentor
    
    # Validate role
    if new_role not in ["admin", "mentor", None]:
        raise HTTPException(
            status_code=400, 
            detail="Invalid role. Must be 'admin', 'mentor', or null"
        )
    
    # Prevent self-demotion
    if user_id == str(current_user.user_id) and new_role != "admin":
        raise HTTPException(
            status_code=400, 
            detail="Cannot remove your own admin role"
        )
    
    supabase = get_supabase_admin_client()
    
    try:
        update_fields = {"role": new_role}
        if new_role == "mentor" and new_is_mentor is None:
            update_fields["is_mentor"] = True
        elif new_role is None and new_is_mentor is None:
            update_fields["is_mentor"] = False
        elif new_is_mentor is not None:
            update_fields["is_mentor"] = new_is_mentor

        # Update user role / mentor flag
        response = supabase.table("users").update(update_fields).eq("id", user_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        updated_user = response.data[0]

        # Sync role/is_mentor into Supabase Auth app_metadata
        try:
            admin_user = supabase.auth.admin.get_user_by_id(user_id)
            app_metadata = (admin_user.user.app_metadata or {}) if admin_user and admin_user.user else {}

            if new_role is None:
                app_metadata.pop("role", None)
            else:
                app_metadata["role"] = new_role

            if new_is_mentor is not None:
                app_metadata["is_mentor"] = new_is_mentor
            elif new_role == "mentor":
                app_metadata["is_mentor"] = True
            elif new_role is None:
                app_metadata["is_mentor"] = False

            supabase.auth.admin.update_user_by_id(
                user_id,
                {"app_metadata": app_metadata}
            )
        except Exception as meta_error:
            print(f"[AdminUsers] Failed to sync app_metadata: {meta_error}")
        
        return {
            "id": updated_user["id"],
            "email": updated_user["email"],
            "role": updated_user.get("role"),
            "created_at": updated_user["created_at"],
            "updated_at": updated_user.get("updated_at", updated_user["created_at"]),
            "message": f"User role updated to {new_role or 'no role'}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to update user role: {str(e)}"
        )
