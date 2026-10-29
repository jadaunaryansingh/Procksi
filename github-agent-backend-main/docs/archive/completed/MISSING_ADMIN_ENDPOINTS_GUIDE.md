# Missing Admin Endpoints Implementation Guide

## Overview

The frontend admin portal requires 2 endpoints that are currently not implemented in the backend:

1. `GET /api/admin/users` - List all users
2. `PATCH /api/admin/users/{userId}/role` - Update user role

---

## Implementation Plan

### File Structure
```
src/api/backend/routers/
└── admin_users.py (NEW)  ← Create this file
```

### Registration
Add to `main.py`:
```python
from src.api.backend.routers import admin_users

app.include_router(admin_users.router)
```

---

## Endpoint 1: List Users

### Frontend Hook (already exists)
```typescript
// File: Github-agent/src/hooks/admin/useUsers.ts
export function useUsers() {
  return useQuery({
    queryKey: ["admin", "users"],
    queryFn: async () => {
      const response = await apiClient.get<UsersResponse>("/api/admin/users");
      return response.data.users;
    },
  });
}
```

### Frontend Type (already exists)
```typescript
export interface User {
  id: string;
  email: string;
  role: "admin" | "mentor" | null;
  created_at: string;
  last_sign_in_at: string | null;
}

interface UsersResponse {
  users: User[];
}
```

### Backend Implementation Needed

```python
"""
Admin User Management Router
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from datetime import datetime

from ..middleware.auth import get_current_user
from ..database import get_supabase
from ..schemas import UserListResponse, User

router = APIRouter(prefix="/api/admin", tags=["admin-users"])


@router.get("/users", response_model=UserListResponse)
async def list_users(current_user: dict = Depends(get_current_user)):
    """
    List all users with their roles.
    Admin only.
    
    Returns:
        - users: Array of user objects with id, email, role, timestamps
    """
    # Verify admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase()
    
    # Query Supabase auth users
    try:
        # Get users from auth.users (requires service role key)
        # For now, we'll query from our users table if it exists
        # Or use Supabase Admin API
        
        # Option 1: If you have a users table with role metadata
        response = supabase.table("users").select(
            "id, email, role, created_at, last_sign_in_at"
        ).order("created_at", desc=True).execute()
        
        users = []
        for user in response.data:
            users.append({
                "id": user["id"],
                "email": user["email"],
                "role": user.get("role"),  # "admin" | "mentor" | null
                "created_at": user["created_at"],
                "last_sign_in_at": user.get("last_sign_in_at")
            })
        
        return {"users": users}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch users: {str(e)}")
```

---

## Endpoint 2: Update User Role

### Frontend Hook (already exists)
```typescript
// File: Github-agent/src/hooks/admin/useUpdateUserRole.ts
export function useUpdateUserRole() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ userId, role }: UpdateRoleParams) => {
      const response = await apiClient.patch(
        `/api/admin/users/${userId}/role`, 
        { role }
      );
      return response.data;
    },
    onSuccess: (_, { role }) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      toast.success(`User role updated to ${role}`);
    },
  });
}
```

### Backend Implementation Needed

```python
@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    request: dict,  # {"role": "admin" | "mentor" | null}
    current_user: dict = Depends(get_current_user)
):
    """
    Update user role (admin/mentor/null).
    Admin only.
    
    Args:
        - user_id: UUID of user to update
        - role: New role ("admin", "mentor", or null)
    
    Returns:
        - Updated user object
    """
    # Verify admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    new_role = request.get("role")
    
    # Validate role
    if new_role not in ["admin", "mentor", None]:
        raise HTTPException(
            status_code=400, 
            detail="Invalid role. Must be 'admin', 'mentor', or null"
        )
    
    supabase = get_supabase()
    
    try:
        # Update user role in database
        response = supabase.table("users").update({
            "role": new_role,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", user_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        updated_user = response.data[0]
        
        return {
            "id": updated_user["id"],
            "email": updated_user["email"],
            "role": updated_user["role"],
            "created_at": updated_user["created_at"],
            "updated_at": updated_user["updated_at"],
            "message": f"User role updated to {new_role or 'no role'}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to update user role: {str(e)}"
        )
```

---

## Complete File: admin_users.py

```python
"""
Admin User Management Router
Endpoints for managing user roles and permissions.
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from ..middleware.auth import get_current_user
from ..database import get_supabase

router = APIRouter(prefix="/api/admin", tags=["admin-users"])


# Schemas
class UserResponse(BaseModel):
    id: str
    email: str
    role: Optional[str] = None  # "admin" | "mentor" | null
    created_at: str
    last_sign_in_at: Optional[str] = None
    full_name: Optional[str] = None


class UserListResponse(BaseModel):
    users: List[UserResponse]


class UpdateRoleRequest(BaseModel):
    role: Optional[str]  # "admin" | "mentor" | null


class UpdateRoleResponse(BaseModel):
    id: str
    email: str
    role: Optional[str]
    created_at: str
    updated_at: str
    message: str


@router.get("/users", response_model=UserListResponse)
async def list_users(current_user: dict = Depends(get_current_user)):
    """
    List all users with their roles.
    Admin only.
    """
    # Verify admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase()
    
    try:
        # Query users table
        response = supabase.table("users").select(
            "id, email, role, created_at, last_sign_in_at, full_name"
        ).order("created_at", desc=True).execute()
        
        users = []
        for user in response.data:
            users.append({
                "id": user["id"],
                "email": user["email"],
                "role": user.get("role"),
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
    current_user: dict = Depends(get_current_user)
):
    """
    Update user role (admin/mentor/null).
    Admin only.
    """
    # Verify admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    new_role = request.role
    
    # Validate role
    if new_role not in ["admin", "mentor", None]:
        raise HTTPException(
            status_code=400, 
            detail="Invalid role. Must be 'admin', 'mentor', or null"
        )
    
    # Prevent self-demotion
    if user_id == current_user.get("id") and new_role != "admin":
        raise HTTPException(
            status_code=400, 
            detail="Cannot remove your own admin role"
        )
    
    supabase = get_supabase()
    
    try:
        # Update user role
        response = supabase.table("users").update({
            "role": new_role,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", user_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        updated_user = response.data[0]
        
        return {
            "id": updated_user["id"],
            "email": updated_user["email"],
            "role": updated_user["role"],
            "created_at": updated_user["created_at"],
            "updated_at": updated_user["updated_at"],
            "message": f"User role updated to {new_role or 'no role'}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to update user role: {str(e)}"
        )
```

---

## Database Requirements

### Users Table Schema

Ensure your Supabase database has a `users` table with:

```sql
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    full_name TEXT,
    role TEXT CHECK (role IN ('admin', 'mentor')),  -- null is allowed
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_sign_in_at TIMESTAMP WITH TIME ZONE
);

-- Index for faster queries
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_email ON users(email);

-- RLS Policies (if using Row Level Security)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Admin can see all users
CREATE POLICY "Admins can view all users"
ON users FOR SELECT
USING (
    auth.jwt() ->> 'role' = 'admin'
);

-- Admin can update user roles
CREATE POLICY "Admins can update user roles"
ON users FOR UPDATE
USING (
    auth.jwt() ->> 'role' = 'admin'
);
```

---

## Testing

### Test GET /api/admin/users

```bash
# With admin token
curl -X GET http://localhost:8000/api/admin/users \
  -H "Authorization: Bearer <admin_jwt_token>"

# Expected Response:
{
  "users": [
    {
      "id": "uuid-1",
      "email": "admin@example.com",
      "role": "admin",
      "created_at": "2024-01-15T10:00:00Z",
      "last_sign_in_at": "2024-01-17T14:30:00Z",
      "full_name": "Admin User"
    },
    {
      "id": "uuid-2",
      "email": "mentor@example.com",
      "role": "mentor",
      "created_at": "2024-01-16T11:00:00Z",
      "last_sign_in_at": "2024-01-17T13:00:00Z",
      "full_name": "Mentor User"
    }
  ]
}
```

### Test PATCH /api/admin/users/{userId}/role

```bash
# Promote user to mentor
curl -X PATCH http://localhost:8000/api/admin/users/uuid-2/role \
  -H "Authorization: Bearer <admin_jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{"role": "mentor"}'

# Expected Response:
{
  "id": "uuid-2",
  "email": "mentor@example.com",
  "role": "mentor",
  "created_at": "2024-01-16T11:00:00Z",
  "updated_at": "2024-01-17T15:00:00Z",
  "message": "User role updated to mentor"
}

# Demote user (remove role)
curl -X PATCH http://localhost:8000/api/admin/users/uuid-2/role \
  -H "Authorization: Bearer <admin_jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{"role": null}'
```

---

## Security Considerations

1. **Admin-only access:**
   - Both endpoints require `role: "admin"` in JWT token
   - Middleware validates token and extracts role claim

2. **Self-protection:**
   - Prevent admin from removing their own admin role
   - Ensure at least one admin always exists

3. **Role validation:**
   - Only allow "admin", "mentor", or null
   - Reject invalid role values

4. **RLS (Row Level Security):**
   - Configure Supabase RLS policies
   - Ensure users can only be viewed/modified by admins

---

## Integration Checklist

- [ ] Create `src/api/backend/routers/admin_users.py`
- [ ] Copy the complete implementation above
- [ ] Add router import in `main.py`
- [ ] Register router: `app.include_router(admin_users.router)`
- [ ] Verify users table exists in Supabase
- [ ] Add RLS policies (if using Row Level Security)
- [ ] Test GET /api/admin/users with admin token
- [ ] Test PATCH /api/admin/users/{id}/role with admin token
- [ ] Test with non-admin token (should return 403)
- [ ] Verify frontend admin portal displays users
- [ ] Test role update from frontend UI

---

## Estimated Time

- **Implementation:** 1-2 hours
- **Testing:** 30 minutes
- **Frontend verification:** 15 minutes

**Total:** ~2-3 hours

---

**Last Updated:** January 2025  
**Status:** Ready for implementation
