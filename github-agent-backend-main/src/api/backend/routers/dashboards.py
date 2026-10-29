"""
Dashboard API endpoints for admin and mentor dashboards.
Provides real-time statistics and overview for batch management.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime, timedelta

from ..middleware.auth import get_current_user, AuthUser
from ..database import get_supabase, get_supabase_admin_client
from ..schemas import (
    AdminDashboardResponse,
    MentorDashboardResponse,
    UserListResponse,
    UserRoleUpdateRequest,
    UserRoleUpdateResponse
)

router = APIRouter(prefix="/api", tags=["dashboards"])


def _parse_timestamp(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _is_active(last_activity, created_at, days: int = 7) -> bool:
    ts = _parse_timestamp(last_activity) or _parse_timestamp(created_at)
    if not ts:
        return False
    if ts.tzinfo:
        return ts >= datetime.now(ts.tzinfo) - timedelta(days=days)
    return ts >= datetime.utcnow() - timedelta(days=days)


@router.get("/admin/dashboard", response_model=AdminDashboardResponse)
async def get_admin_dashboard(
    batchId: str = Query(..., description="Batch ID to get dashboard for"),
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Get admin dashboard overview for a specific batch.
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase_admin_client()
    
    # Verify batch exists
    batch_response = supabase.table("batches").select("id, name").eq("id", batchId).execute()
    if not batch_response.data:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    batch = batch_response.data[0]
    
    # Get total teams count
    teams_response = supabase.table("teams").select(
        "id, health_status, mentor_id, last_activity, created_at, team_name"
    ).eq("batch_id", batchId).execute()
    teams = teams_response.data or []
    
    # Calculate overview stats
    total_teams = len(teams)
    active_teams = len([t for t in teams if _is_active(t.get("last_activity"), t.get("created_at"))])
    inactive_teams = total_teams - active_teams
    unassigned_teams = len([t for t in teams if not t.get("mentor_id")])
    
    # Get health distribution from stored health_status
    health_dist = {
        "onTrack": len([t for t in teams if t.get("health_status") == "on_track"]),
        "atRisk": len([t for t in teams if t.get("health_status") == "at_risk"]),
        "critical": len([t for t in teams if t.get("health_status") == "critical"])
    }
    # Count teams with no/null health_status as "on_track"
    null_health = total_teams - (health_dist["onTrack"] + health_dist["atRisk"] + health_dist["critical"])
    health_dist["onTrack"] += null_health
    
    # Get total students count (from students table)
    team_ids = [t.get("id") for t in teams if t.get("id")]
    if team_ids:
        students_response = supabase.table("students").select("id", count="exact").in_("team_id", team_ids).execute()
        total_students = students_response.count or 0
    else:
        total_students = 0
    
    # Get total mentors count (unique mentors assigned to teams)
    unique_mentors = set(t.get("mentor_id") for t in teams if t.get("mentor_id"))
    total_mentors = len(unique_mentors)
    
    # Get analysis queue count (teams with status 'pending' or 'processing')
    # For now, we'll set this to 0 as we don't have an analysis queue table yet
    analysis_queue = 0
    
    # Get recent activity (last 10 activities)
    # We'll simulate this with team creation and updates
    # Reuse already-fetched teams for recent activity (no extra query needed)
    recent_activity = []
    for team in sorted(teams, key=lambda t: t.get("created_at", ""), reverse=True)[:5]:
        recent_activity.append({
            "id": team["id"],
            "type": "team_created",
            "message": "New team added",
            "teamName": team["team_name"],
            "timestamp": team["created_at"]
        })
    
    # Sort by timestamp and limit to 10
    recent_activity.sort(key=lambda x: x["timestamp"], reverse=True)
    recent_activity = recent_activity[:10]
    
    # Get mentor workload (OPTIMIZED: Single batch query instead of N queries)
    admin_supabase = get_supabase_admin_client()
    mentor_workload = []
    
    if unique_mentors:
        # Batch fetch all mentors in one query (was: N separate queries)
        mentor_response = admin_supabase.table("users").select(
            "id, full_name, email"
        ).in_("id", list(unique_mentors)).execute()
        
        # Build lookup dictionary
        mentor_lookup = {str(m["id"]): m for m in mentor_response.data or []}
        
        # Pre-aggregate team stats per mentor (in-memory, but faster than N queries)
        mentor_stats = {}
        for team in teams:
            mid = str(team.get("mentor_id"))
            if not mid or mid not in unique_mentors:
                continue
            
            if mid not in mentor_stats:
                mentor_stats[mid] = {"assigned": 0, "on_track": 0, "at_risk": 0}
            
            mentor_stats[mid]["assigned"] += 1
            health = team.get("health_status")
            if health == "on_track":
                mentor_stats[mid]["on_track"] += 1
            elif health == "at_risk":
                mentor_stats[mid]["at_risk"] += 1
        
        # Build workload array from aggregated stats
        for mentor_id, stats in mentor_stats.items():
            mentor = mentor_lookup.get(mentor_id)
            if not mentor:
                continue
            
            mentor_workload.append({
                "mentorId": mentor_id,
                "mentorName": mentor.get("full_name") or mentor.get("email") or "Unknown Mentor",
                "assignedTeams": stats["assigned"],
                "onTrack": stats["on_track"],
                "atRisk": stats["at_risk"]
            })
        
        # Sort by assigned teams descending
        mentor_workload.sort(key=lambda x: x["assignedTeams"], reverse=True)
    
    return {
        "batchId": batchId,
        "batchName": batch["name"],
        "overview": {
            "totalTeams": total_teams,
            "activeTeams": active_teams,
            "inactiveTeams": inactive_teams,
            "totalMentors": total_mentors,
            "totalStudents": total_students,
            "unassignedTeams": unassigned_teams,
            "analysisQueue": analysis_queue
        },
        "healthDistribution": health_dist,
        "recentActivity": recent_activity,
        "mentorWorkload": mentor_workload
    }


@router.get("/admin/users", response_model=UserListResponse)
async def get_admin_users(
    role: Optional[str] = Query(None, description="Filter by role: admin or mentor"),
    search: Optional[str] = Query(None, description="Search by name or email"),
    page: int = Query(1, ge=1, description="Page number"),
    pageSize: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Get all users with role management.
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase_admin_client()
    
    # Build query
    query = supabase.table("users").select("*")
    
    # Apply filters
    if role:
        if role not in ["admin", "mentor"]:
            raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin' or 'mentor'")
        query = query.eq("role", role)
    
    # For search, we need to use ilike (case-insensitive LIKE)
    if search:
        # Note: Supabase doesn't support OR conditions easily, so we'll filter in Python
        all_users_response = query.execute()
        users = all_users_response.data or []
        
        # Filter by search term
        search_lower = search.lower()
        users = [
            u for u in users
            if search_lower in (u.get("full_name") or "").lower()
            or search_lower in (u.get("email") or "").lower()
        ]
    else:
        all_users_response = query.execute()
        users = all_users_response.data or []
    
    # Sort by created_at descending
    users.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    # Calculate total
    total = len(users)
    
    # Apply pagination
    start = (page - 1) * pageSize
    end = start + pageSize
    users_page = users[start:end]
    
    # Format response
    formatted_users = []
    for user in users_page:
        formatted_users.append({
            "id": user["id"],
            "email": user.get("email", ""),
            "fullName": user.get("full_name") or "",
            "role": user.get("role", "mentor"),
            "status": user.get("status", "active"),
            "lastLogin": user.get("last_login"),
            "createdAt": user.get("created_at")
        })
    
    return {
        "users": formatted_users,
        "total": total,
        "page": page,
        "pageSize": pageSize
    }


@router.put("/admin/users/{userId}/role", response_model=UserRoleUpdateResponse)
async def update_user_role(
    userId: str,
    request: UserRoleUpdateRequest,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Change user role.
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Validate role
    if request.role not in ["admin", "mentor"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin' or 'mentor'")
    
    supabase = get_supabase()
    
    # Check if user exists
    user_response = supabase.table("users").select("*").eq("id", userId).execute()
    if not user_response.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update user role
    update_response = supabase.table("users").update({
        "role": request.role,
        "updated_at": datetime.utcnow().isoformat()
    }).eq("id", userId).execute()
    
    if not update_response.data:
        raise HTTPException(status_code=500, detail="Failed to update user role")
    
    updated_user = update_response.data[0]
    
    return {
        "user": {
            "id": updated_user["id"],
            "email": updated_user.get("email", ""),
            "fullName": updated_user.get("full_name", ""),
            "role": updated_user.get("role", "mentor"),
            "status": updated_user.get("status", "active"),
            "lastLogin": updated_user.get("last_login"),
            "createdAt": updated_user.get("created_at")
        },
        "message": "User role updated successfully"
    }


# NOTE: Mentor dashboard endpoints have been moved to mentor_dashboard.py
# The old /api/mentor/dashboard and /api/mentor/teams routes are now handled by the new router
# which provides better filtering based on mentor assignments (including junction table support)

