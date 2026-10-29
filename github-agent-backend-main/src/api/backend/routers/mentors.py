"""
Mentor Management Router - Phase 3
Handles all mentor CRUD operations and mentor-related endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime
from uuid import UUID

from ..schemas import (
    MentorResponse, MentorDetailResponse, MentorListResponse,
    MentorCreateRequest, MentorUpdateRequest,
    MessageResponse
)
from ..middleware import get_current_user, RoleChecker, AuthUser
from ..database import get_supabase, get_supabase_admin_client

router = APIRouter(prefix="/api/mentors", tags=["Mentors"])


@router.get("", response_model=MentorListResponse, dependencies=[Depends(RoleChecker(["admin"]))])
async def list_mentors(
    batch_id: Optional[UUID] = Query(None, description="Filter mentors by batch"),
    search: Optional[str] = Query(None, description="Search by name or email"),
    status: Optional[str] = Query(None, description="Filter by status"),
    sort: str = Query("full_name", description="Sort field"),
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Get all mentors (admin only).
    
    Returns list of mentors with team counts and batch assignments.
    """
    supabase = get_supabase_admin_client()
    
    # Query users with mentor role
    query = supabase.table("users").select(
        """
        id,
        email,
        full_name,
        avatar_url,
        status,
        created_at
        """,
        count="exact"
    ).or_("role.eq.mentor,is_mentor.eq.true")
    
    # Apply filters
    if status:
        query = query.eq("status", status)
    
    if search:
        query = query.or_(
            f"full_name.ilike.%{search}%,"
            f"email.ilike.%{search}%"
        )
    
    # Apply sorting
    if sort.startswith("-"):
        query = query.order(sort[1:], desc=True)
    else:
        query = query.order(sort)
    
    # Execute query
    response = query.execute()
    mentors_data = response.data
    
    # Enrich with team counts and batches — SINGLE batch query instead of N queries
    mentors_data = response.data
    mentor_ids = [m["id"] for m in mentors_data]

    if mentor_ids:
        teams_q = supabase.table("teams").select("id, batch_id, mentor_id")
        if batch_id:
            teams_q = teams_q.eq("batch_id", str(batch_id))
        teams_q = teams_q.in_("mentor_id", mentor_ids)
        all_teams = teams_q.execute().data or []

        from collections import defaultdict
        teams_by_mentor: dict = defaultdict(list)
        for t in all_teams:
            teams_by_mentor[t["mentor_id"]].append(t)

        for mentor in mentors_data:
            teams = teams_by_mentor.get(mentor["id"], [])
            mentor["team_count"] = len(teams)
            mentor["batches"] = list({t["batch_id"] for t in teams if t.get("batch_id")})
    else:
        for mentor in mentors_data:
            mentor["team_count"] = 0
            mentor["batches"] = []
    
    return MentorListResponse(
        mentors=mentors_data,
        total=len(mentors_data)
    )


@router.post("", response_model=MentorResponse, dependencies=[Depends(RoleChecker(["admin"]))])
async def create_mentor(
    mentor_data: MentorCreateRequest,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Add a new mentor (admin only).
    
    Creates a user account with mentor role. The mentor must sign in with Google OAuth.
    """
    supabase = get_supabase_admin_client()
    
    # Check if user already exists
    existing_user = supabase.table("users").select("id, email, role, status").eq("email", mentor_data.email).execute()
    
    status = mentor_data.status or "active"

    if existing_user.data:
        existing = existing_user.data[0]
        update_fields = {
            "full_name": mentor_data.full_name,
            "status": status,
            "is_mentor": True,
            "updated_at": datetime.utcnow().isoformat()
        }
        if existing.get("role") != "admin":
            update_fields["role"] = "mentor"

        update_response = supabase.table("users").update(update_fields).eq("id", existing["id"]).execute()
        updated_user = (update_response.data or [existing])[0]
        mentor_record = updated_user
    else:
        user_insert = {
            "email": mentor_data.email,
            "full_name": mentor_data.full_name,
            "role": "mentor",
            "is_mentor": True,
            "status": status,
            "created_at": datetime.utcnow().isoformat()
        }
        insert_response = supabase.table("users").insert(user_insert).execute()
        mentor_record = (insert_response.data or [user_insert])[0]

    return MentorResponse(
        mentor={
            "id": mentor_record.get("id"),
            "email": mentor_record.get("email", mentor_data.email),
            "full_name": mentor_record.get("full_name", mentor_data.full_name),
            "role": mentor_record.get("role", "mentor"),
            "status": mentor_record.get("status", status),
            "team_count": 0,
            "batches": []
        },
        message=(
            f"Mentor record created for {mentor_data.email}. "
            "They must sign in with Google to activate their account."
        )
    )


@router.get("/{mentor_id}", response_model=MentorDetailResponse, dependencies=[Depends(RoleChecker(["admin"]))])
async def get_mentor(
    mentor_id: UUID,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Get mentor details with assigned teams.
    
    Returns complete mentor profile with all team assignments.
    """
    # Use admin client to bypass RLS policies on users table
    supabase = get_supabase_admin_client()
    
    # Get mentor user
    mentor_response = supabase.table("users").select(
        "id, email, full_name, avatar_url, status, role, created_at, is_mentor"
    ).eq("id", str(mentor_id)).or_("role.eq.mentor,is_mentor.eq.true").execute()
    
    if not mentor_response.data:
        raise HTTPException(status_code=404, detail="Mentor not found")
    
    mentor = mentor_response.data[0]
    
    # Get assigned teams
    teams_response = supabase.table("teams").select(
        """
        id,
        team_name,
        batch_id,
        status,
        health_status,
        last_activity,
        batches!inner(id, name)
        """
    ).eq("mentor_id", str(mentor_id)).execute()
    
    teams = teams_response.data or []
    
    # Format assigned teams
    assigned_teams = []
    unique_batches = set()
    
    for team in teams:
        batch = team.get("batches", {})
        if isinstance(batch, list):
            batch = batch[0] if batch else {}
        
        batch_id = batch.get("id") if batch else team.get("batch_id")
        batch_name = batch.get("name") if batch else "Unknown"
        
        if batch_id:
            unique_batches.add(batch_id)
        
        assigned_teams.append({
            "team_id": team["id"],
            "team_name": team.get("team_name"),
            "batch_id": batch_id,
            "batch_name": batch_name,
            "status": team.get("status"),
            "health_status": team.get("health_status"),
            "last_activity": team.get("last_activity")
        })
    
    return MentorDetailResponse(
        id=mentor["id"],
        email=mentor["email"],
        full_name=mentor.get("full_name"),
        avatar_url=mentor.get("avatar_url"),
        status=mentor.get("status", "active"),
        assigned_teams=assigned_teams,
        team_count=len(assigned_teams),
        batches=list(unique_batches),
        created_at=mentor["created_at"]
    )


@router.put("/{mentor_id}", response_model=MentorResponse, dependencies=[Depends(RoleChecker(["admin"]))])
async def update_mentor(
    mentor_id: UUID,
    mentor_data: MentorUpdateRequest,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Update mentor details (admin only).
    
    Allows updating mentor's full name and status.
    """
    supabase = get_supabase()
    
    # Check if mentor exists
    existing_mentor = supabase.table("users").select("id, role, is_mentor").eq("id", str(mentor_id)).or_("role.eq.mentor,is_mentor.eq.true").execute()
    
    if not existing_mentor.data:
        raise HTTPException(status_code=404, detail="Mentor not found")
    
    # Build update data
    update_data = {}
    if mentor_data.full_name is not None:
        update_data["full_name"] = mentor_data.full_name
    if mentor_data.status is not None:
        update_data["status"] = mentor_data.status
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # Update mentor
    mentor_response = supabase.table("users").update(update_data).eq("id", str(mentor_id)).execute()
    
    if not mentor_response.data:
        raise HTTPException(status_code=500, detail="Failed to update mentor")
    
    # Get updated mentor with team count
    updated_mentor = mentor_response.data[0]
    
    # Get team count
    teams_response = supabase.table("teams").select("id", count="exact").eq("mentor_id", str(mentor_id)).execute()
    updated_mentor["team_count"] = teams_response.count or 0
    
    return MentorResponse(
        mentor=updated_mentor,
        message="Mentor updated successfully"
    )


@router.delete("/{mentor_id}", response_model=MessageResponse, dependencies=[Depends(RoleChecker(["admin"]))])
async def delete_mentor(
    mentor_id: UUID,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Remove a mentor (admin only).
    
    Unassigns all teams and removes mentor account.
    """
    supabase = get_supabase()
    
    # Check if mentor exists
    existing_mentor = supabase.table("users").select("id, role, is_mentor").eq("id", str(mentor_id)).or_("role.eq.mentor,is_mentor.eq.true").execute()
    
    if not existing_mentor.data:
        raise HTTPException(status_code=404, detail="Mentor not found")
    
    # Count teams before unassigning
    teams_response = supabase.table("teams").select("id", count="exact").eq("mentor_id", str(mentor_id)).execute()
    team_count = teams_response.count or 0
    
    # Unassign all teams
    if team_count > 0:
        supabase.table("teams").update({"mentor_id": None}).eq("mentor_id", str(mentor_id)).execute()
    
    # Delete mentor_team_assignments
    supabase.table("mentor_team_assignments").delete().eq("mentor_id", str(mentor_id)).execute()
    
    # Delete user account
    supabase.table("users").delete().eq("id", str(mentor_id)).execute()
    
    return MessageResponse(
        success=True,
        message=f"Mentor removed successfully. {team_count} teams unassigned."
    )
