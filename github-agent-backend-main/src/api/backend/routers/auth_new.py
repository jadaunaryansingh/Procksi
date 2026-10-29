"""
Authentication Router
Handles user authentication, profile management, and role verification
"""
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from pydantic import BaseModel, Field
from starlette.requests import Request
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from ..schemas import (
    LoginRequest,
    LoginResponse,
    UserProfileResponse,
    UserUpdateRequest,
    ErrorResponse
)
from ..middleware import get_current_user, AuthUser
from ..database import get_supabase_client, get_supabase_admin_client
from ..utils.rate_limiter import limiter

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


_HONORIFICS_AUTH = {"dr.", "dr", "prof.", "prof", "mr.", "mr", "ms.", "ms",
                    "mrs.", "mrs", "shri", "smt.", "smt", "er.", "er", "col.", "col"}


def _normalize_name_auth(name: str) -> str:
    """Strip honorific prefixes and normalise whitespace for fuzzy matching."""
    parts = name.lower().strip().split()
    while parts and parts[0] in _HONORIFICS_AUTH:
        parts.pop(0)
    return " ".join(parts)


def _auto_assign_mentor_teams(admin_client, user_id: str, full_name: str, email: str = "") -> int:
    """
    Auto-assign teams to a mentor on login.

    Matching order (stops at first successful match):
      1. metadata->ingestion->mentor == mentor's full_name  (exact, case-insensitive)
      2. metadata->ingestion->mentor_email == mentor's email  (case-insensitive)
      3. metadata->suggested_mentor == mentor's full_name or email
      4. Honorific-stripped name match (e.g. "Dr. Jane" matches registered name "Jane")

    If full_name is not available from the Google account (e.g. email-only
    accounts), the function first looks up the name already stored in the
    users table (pre-populated by an admin).  Login is never blocked.
    """
    try:
        # --- resolve name: Google metadata > users table ---
        resolved_name = (full_name or "").strip()
        if not resolved_name:
            try:
                db_user = admin_client.table("users").select("full_name").eq("id", user_id).single().execute()
                resolved_name = ((db_user.data or {}).get("full_name") or "").strip()
            except Exception:
                pass

        resolved_email = (email or "").strip().lower()
        resolved_name_norm = _normalize_name_auth(resolved_name) if resolved_name else ""

        if not resolved_name and not resolved_email:
            print(f"[Auth] Auto-assign skipped for {user_id}: no name or email to match")
            return 0

        # Find unassigned teams whose ingestion metadata names this mentor
        teams_resp = admin_client.table("teams").select(
            "id, team_name, batch_id, metadata"
        ).is_("mentor_id", "null").execute()

        teams_to_assign = []
        for team in (teams_resp.data or []):
            metadata = team.get("metadata") or {}
            ingestion = metadata.get("ingestion") or {}
            ingestion_mentor = (ingestion.get("mentor") or "").strip()
            ingestion_mentor_email = (ingestion.get("mentor_email") or "").strip().lower()
            suggested_mentor = (metadata.get("suggested_mentor") or "").strip()

            name_match = bool(resolved_name and ingestion_mentor.lower() == resolved_name.lower())
            email_match = bool(resolved_email and ingestion_mentor_email and ingestion_mentor_email == resolved_email)

            # Honorific-stripped name match
            norm_match = False
            if resolved_name_norm:
                norm_match = (_normalize_name_auth(ingestion_mentor) == resolved_name_norm or
                              _normalize_name_auth(suggested_mentor) == resolved_name_norm)

            # suggested_mentor exact match (may be name or email)
            suggested_match = bool(
                (resolved_name and suggested_mentor.lower() == resolved_name.lower()) or
                (resolved_email and suggested_mentor.lower() == resolved_email)
            )

            if name_match or email_match or norm_match or suggested_match:
                teams_to_assign.append(team)

        if not teams_to_assign:
            return 0

        now_iso = datetime.utcnow().isoformat()
        assigned = 0
        for team in teams_to_assign:
            team_id = team["id"]
            try:
                # Set mentor_id on the team
                admin_client.table("teams").update(
                    {"mentor_id": user_id}
                ).eq("id", team_id).execute()

                # Upsert mentor_team_assignments record
                existing = admin_client.table("mentor_team_assignments").select("id").eq(
                    "mentor_id", user_id
                ).eq("team_id", team_id).execute()
                if not existing.data:
                    admin_client.table("mentor_team_assignments").insert({
                        "mentor_id": user_id,
                        "team_id": team_id,
                        "batch_id": team.get("batch_id"),
                        "assigned_by": user_id,
                        "assigned_at": now_iso,
                    }).execute()
                assigned += 1
                print(f"[Auth] Auto-assigned team '{team.get('team_name')}' to mentor {full_name}")
            except Exception as team_err:
                print(f"[Auth] Failed to auto-assign team {team_id}: {team_err}")

        if assigned:
            # Clear mentor cache keys so dashboard refreshes immediately
            try:
                from ..utils.cache import cache
                for key in [
                    f"hackeval:mentor:team_ids:{user_id}",
                    f"hackeval:mentor:dashboard:{user_id}",
                    f"hackeval:mentor:reports:{user_id}:all",
                    "hackeval:mentors:lookup",
                ]:
                    cache.delete(key)
            except Exception:
                pass

        print(f"[Auth] Auto-assigned {assigned} team(s) to mentor '{full_name}' ({user_id})")
        return assigned
    except Exception as e:
        print(f"[Auth] Auto-assign failed for mentor {user_id}: {e}")
        return 0


@router.post("/login", response_model=LoginResponse, responses={401: {"model": ErrorResponse}})
@limiter.limit("5/minute")
async def login(request: Request, login_data: LoginRequest, background_tasks: BackgroundTasks):
    """
    Authenticate user with Google OAuth ID token
    
    **Process:**
    1. Verify Google ID token with Supabase
    2. Create/update user in database
    3. Return JWT tokens and user profile
    
    **Returns:**
    - access_token: JWT token for API requests
    - refresh_token: Token to refresh access token
    - user: User profile with role
    """
    try:
        supabase = get_supabase_client()
        
        # Sign in with ID token (Supabase handles Google verification)
        auth_response = supabase.auth.sign_in_with_id_token({
            "provider": "google",
            "token": login_data.id_token
        })
        
        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Google ID token"
            )
        
        user = auth_response.user
        session = auth_response.session
        
        # Get user metadata
        user_metadata = user.user_metadata or {}
        app_metadata = user.app_metadata or {}
        
        # Get role (do not default to mentor for existing revoked users)
        role = app_metadata.get("role") or user_metadata.get("role")
        
        admin_client = get_supabase_admin_client()

        # Ensure users table is synced on login
        try:
            user_id = str(user.id)
            existing_user = admin_client.table("users").select("id, role, is_mentor").eq("id", user_id).limit(1).execute()
            existing_record = existing_user.data[0] if existing_user.data else None

            existing_role = existing_record.get("role") if existing_record else None
            desired_role = role if role else (existing_role if existing_record else "mentor")
            if existing_record and existing_role == "admin":
                desired_role = "admin"

            role = desired_role
            desired_is_mentor = bool(app_metadata.get("is_mentor"))
            if role == "mentor":
                desired_is_mentor = True
            if existing_record and existing_record.get("is_mentor") is True:
                desired_is_mentor = True

            profile_full_name = user_metadata.get("full_name") or user_metadata.get("name")
            now_iso = datetime.utcnow().isoformat()

            if existing_record:
                update_fields = {
                    "is_mentor": desired_is_mentor,
                    "updated_at": now_iso,
                    "last_login": now_iso,
                    "is_online": True
                }
                if role is not None and existing_role != role:
                    update_fields["role"] = role
                if profile_full_name:
                    update_fields["full_name"] = profile_full_name
                print(f"[Auth][DEBUG] Updating user {user_id} with fields: {update_fields}")
                result = admin_client.table("users").update(update_fields).eq("id", user_id).execute()
                print(f"[Auth][DEBUG] Update result for user {user_id}: {result}")
            else:
                # Convert user.created_at to ISO string if it's a datetime object
                created_at_iso = user.created_at.isoformat() if hasattr(user.created_at, 'isoformat') else (user.created_at or now_iso)
                admin_client.table("users").insert({
                    "id": user_id,
                    "email": user.email,
                    "full_name": profile_full_name,
                    "role": desired_role,
                    "is_mentor": desired_is_mentor,
                    "status": "active",
                    "created_at": created_at_iso,
                    "last_login": now_iso,
                    "is_online": True,
                    "total_time_spent": "0 seconds"
                }).execute()
        except Exception as sync_error:
            print(f"[Auth] Failed to sync users table: {sync_error}")

        # Auto-assign teams when a mentor logs in (only when name is available)
        if role == "mentor" and profile_full_name:
            background_tasks.add_task(
                _auto_assign_mentor_teams,
                admin_client,
                user_id,
                profile_full_name,
                user.email or "",
            )

        # Onboarding required when the mentor has no name yet
        requires_onboarding = (role == "mentor" and not profile_full_name)

        # Build user profile response
        user_profile = UserProfileResponse(
            id=UUID(user.id),
            email=user.email,
            role=role,
            full_name=user_metadata.get("full_name") or user_metadata.get("name"),
            avatar_url=user_metadata.get("avatar_url") or user_metadata.get("picture"),
            created_at=user.created_at
        )
        
        return LoginResponse(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            user=user_profile,
            expires_in=session.expires_in or 3600,
            requires_onboarding=requires_onboarding,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}"
        )


@router.post("/refresh", response_model=LoginResponse)
@limiter.limit("5/minute")
async def refresh_token(request: Request, refresh_token: str):
    """
    Refresh access token using refresh token
    
    **Parameters:**
    - refresh_token: Valid refresh token
    
    **Returns:**
    - New access_token and refresh_token
    """
    try:
        supabase = get_supabase_client()
        
        # Refresh session
        auth_response = supabase.auth.refresh_session(refresh_token)
        
        if not auth_response.user or not auth_response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token"
            )
        
        user = auth_response.user
        session = auth_response.session
        
        # Get user metadata
        user_metadata = user.user_metadata or {}
        app_metadata = user.app_metadata or {}
        role = app_metadata.get("role") or user_metadata.get("role") or "mentor"
        
        user_profile = UserProfileResponse(
            id=UUID(user.id),
            email=user.email,
            role=role,
            full_name=user_metadata.get("full_name") or user_metadata.get("name"),
            avatar_url=user_metadata.get("avatar_url") or user_metadata.get("picture"),
            created_at=user.created_at
        )
        
        return LoginResponse(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            user=user_profile,
            expires_in=session.expires_in or 3600
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token refresh failed: {str(e)}"
        )


@router.get("/me", response_model=UserProfileResponse)
async def get_current_user_profile(
    background_tasks: BackgroundTasks,
    current_user: AuthUser = Depends(get_current_user),
):
    """
    Get current user's profile
    
    **Requires:** Valid JWT token
    
    **Returns:** User profile with FRESH role from Supabase Admin API (cached for 5 minutes)
    """
    from ..database import get_supabase_admin_client
    from ..utils.cache import cache, RedisCache
    
    user_id = str(current_user.user_id)
    admin_client = get_supabase_admin_client()
    
    # Check cache first
    cache_key = f"auth:role:{user_id}"
    cached_role = cache.get(cache_key)
    fresh_metadata = {}
    admin_user_created_at = None
    admin_user_avatar = None

    # Always try to fetch admin user metadata (needed for is_mentor)
    try:
        admin_user = admin_client.auth.admin.get_user_by_id(user_id)

        if admin_user and admin_user.user:
            fresh_metadata = admin_user.user.app_metadata or {}
            admin_user_created_at = admin_user.user.created_at
            user_metadata = admin_user.user.user_metadata or {}
            admin_user_avatar = user_metadata.get("avatar_url") or user_metadata.get("picture")
        else:
            print(f"[Auth] No admin user data for {user_id}")
    except Exception as e:
        print(f"[Auth] Admin API error: {e}")

    if cached_role:
        # Use cached role
        role = cached_role
    else:
        # Cache miss - fetch fresh role from Admin API
        role = fresh_metadata.get("role") or current_user.role or "mentor"
        print(f"[Auth] Fresh role from Admin API: {role} (app_metadata: {fresh_metadata})")

        # Cache the role for 5 minutes
        cache.set(cache_key, role, RedisCache.TTL_MEDIUM)
    
    print(f"[Auth] Final role for {current_user.email}: {role}")
    
    # Check if user has mentor access (app_metadata.is_mentor OR users.is_mentor OR mentors table)
    is_mentor = bool(fresh_metadata.get("is_mentor"))
    try:
        if not is_mentor:
            mentor_flag = admin_client.table("users").select("is_mentor").eq("id", user_id).limit(1).execute()
            if mentor_flag.data:
                is_mentor = bool(mentor_flag.data[0].get("is_mentor"))
        if not is_mentor:
            mentor_result = admin_client.table("mentors").select("id").eq("user_id", user_id).limit(1).execute()
            is_mentor = bool(mentor_result.data)
    except Exception as e:
        print(f"[Auth] Mentor lookup error: {e}")

    # Fetch mentor activity fields from users table
    activity_fields = {
        "last_login": None,
        "last_logout": None,
        "is_online": None,
        "total_time_spent": None
    }
    try:
        user_row = admin_client.table("users").select("last_login, last_logout, is_online, total_time_spent").eq("id", user_id).limit(1).execute()
        if user_row.data:
            row = user_row.data[0]
            activity_fields["last_login"] = row.get("last_login")
            activity_fields["last_logout"] = row.get("last_logout")
            activity_fields["is_online"] = row.get("is_online")
            activity_fields["total_time_spent"] = row.get("total_time_spent")
    except Exception as e:
        print(f"[Auth] Failed to fetch mentor activity fields: {e}")

    # Auto-assign teams for mentors during /me.
    # Use a short cooldown so assignment still runs automatically for mentors
    # who have already logged in before new teams are imported.
    if role in ("mentor",):
        assign_cooldown_key = f"auth:auto_assign_cooldown:{user_id}"
        if not cache.get(assign_cooldown_key):
            background_tasks.add_task(
                _auto_assign_mentor_teams,
                admin_client,
                user_id,
                current_user.full_name or "",
                current_user.email or "",
            )
            # Avoid excessive DB pressure on rapid page refreshes.
            cache.set(assign_cooldown_key, "1", RedisCache.TTL_SHORT)

    return UserProfileResponse(
        id=current_user.user_id,
        email=current_user.email,
        role=role,
        full_name=current_user.full_name,
        avatar_url=admin_user_avatar,
        created_at=admin_user_created_at or datetime.now(timezone.utc),
        is_mentor=is_mentor,
        last_login=activity_fields["last_login"],
        last_logout=activity_fields["last_logout"],
        is_online=activity_fields["is_online"],
        total_time_spent=activity_fields["total_time_spent"]
    )


@router.put("/me", response_model=UserProfileResponse)
async def update_current_user_profile(
    update_data: UserUpdateRequest,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Update current user's profile
    
    **Requires:** Valid JWT token
    
    **Updatable fields:**
    - full_name
    - avatar_url
    
    **Note:** Email and role cannot be changed through this endpoint
    """
    try:
        supabase = get_supabase_client()
        
        # Prepare update data
        user_metadata = {}
        if update_data.full_name is not None:
            user_metadata["full_name"] = update_data.full_name
        if update_data.avatar_url is not None:
            user_metadata["avatar_url"] = update_data.avatar_url
        
        # Update user metadata
        if user_metadata:
            auth_response = supabase.auth.update_user({
                "data": user_metadata
            })
            
            if not auth_response.user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to update profile"
                )
            
            user = auth_response.user
        else:
            # No updates, just return current profile
            user_response = supabase.auth.get_user()
            user = user_response.user
        
        user_metadata = user.user_metadata or {}
        app_metadata = user.app_metadata or {}
        role = app_metadata.get("role") or user_metadata.get("role") or current_user.role
        
        return UserProfileResponse(
            id=UUID(user.id),
            email=user.email,
            role=role,
            full_name=user_metadata.get("full_name") or user_metadata.get("name"),
            avatar_url=user_metadata.get("avatar_url") or user_metadata.get("picture"),
            created_at=user.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}"
        )


@router.post("/logout")
async def logout(current_user: AuthUser = Depends(get_current_user)):
    """
    Logout current user
    
    **Requires:** Valid JWT token
    
    **Effect:** Invalidates current session
    """
    try:
        from dateutil import parser as dateutil_parser
        from datetime import timedelta

        supabase = get_supabase_client()
        admin_client = get_supabase_admin_client()
        user_id = str(current_user.user_id)
        now_dt = datetime.utcnow()
        now_iso = now_dt.isoformat()

        # Fetch last_login and total_time_spent
        user_row = admin_client.table("users").select("last_login, total_time_spent").eq("id", user_id).limit(1).execute()
        last_login = None
        existing_total_seconds = 0

        if user_row.data:
            last_login = user_row.data[0].get("last_login")
            raw_total = user_row.data[0].get("total_time_spent") or "0"
            # Parse existing total_time_spent (PostgreSQL interval string e.g. "01:30:00" or "5400 seconds")
            try:
                # Handle HH:MM:SS format
                if isinstance(raw_total, str) and ":" in raw_total:
                    parts = raw_total.split(":")
                    hours = int(parts[0]) if len(parts) > 0 else 0
                    minutes = int(parts[1]) if len(parts) > 1 else 0
                    seconds = int(float(parts[2])) if len(parts) > 2 else 0
                    existing_total_seconds = hours * 3600 + minutes * 60 + seconds
                elif isinstance(raw_total, str):
                    # Handle "X seconds" or plain number
                    numeric = ''.join(c for c in raw_total if c.isdigit() or c == '.')
                    existing_total_seconds = int(float(numeric)) if numeric else 0
                else:
                    existing_total_seconds = 0
            except Exception:
                existing_total_seconds = 0

        # Calculate session duration in seconds
        session_seconds = 0
        if last_login:
            try:
                last_login_dt = dateutil_parser.isoparse(last_login)
                if last_login_dt.tzinfo is not None:
                    from datetime import timezone
                    now_dt_aware = now_dt.replace(tzinfo=timezone.utc)
                    session_seconds = max(0, int((now_dt_aware - last_login_dt).total_seconds()))
                else:
                    session_seconds = max(0, int((now_dt - last_login_dt).total_seconds()))
            except Exception:
                session_seconds = 0

        # Compute new total as a plain "X seconds" string (valid PostgreSQL interval)
        new_total_seconds = existing_total_seconds + session_seconds
        new_total_interval = f"{new_total_seconds} seconds"

        admin_client.table("users").update({
            "last_logout": now_iso,
            "is_online": False,
            "total_time_spent": new_total_interval
        }).eq("id", user_id).execute()

        # Sign out user
        try:
            supabase.auth.sign_out()
        except Exception:
            pass

        return {"message": "Successfully logged out"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Logout failed: {str(e)}"
        )


# ---------------------------------------------------------------------------
# Onboarding endpoint – called when requires_onboarding=True after login
# ---------------------------------------------------------------------------

class OnboardingRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120, description="Mentor's full name")


class OnboardingResponse(BaseModel):
    success: bool
    full_name: str
    teams_assigned: int


@router.post(
    "/onboarding",
    response_model=OnboardingResponse,
    summary="Complete mentor onboarding (set display name)",
)
@limiter.limit("10/minute")
async def complete_onboarding(
    request: Request,
    payload: OnboardingRequest,
    current_user: AuthUser = Depends(get_current_user),
):
    """
    Save the mentor's display name collected during the onboarding screen.

    After saving the name:
    - Teams whose `metadata.ingestion.mentor` matches this name are automatically
      assigned to the mentor.
    - The response includes how many teams were newly assigned.

    **Requires:** Valid JWT token (mentor or admin)
    """
    if current_user.role not in ("mentor", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only mentors can complete onboarding")

    full_name = payload.full_name.strip()
    user_id = str(current_user.user_id)
    admin_client = get_supabase_admin_client()

    # Persist the name
    try:
        admin_client.table("users").update({
            "full_name": full_name,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", user_id).execute()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save name: {str(e)}",
        )

    # Trigger auto-assignment now that we have a name
    teams_assigned = _auto_assign_mentor_teams(
        admin_client, user_id, full_name, email=current_user.email or ""
    )

    return OnboardingResponse(
        success=True,
        full_name=full_name,
        teams_assigned=teams_assigned,
    )
