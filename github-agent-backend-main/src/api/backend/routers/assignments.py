"""
Assignment Management Router - Phase 3
Handles mentor-team assignment operations
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from uuid import UUID
from datetime import datetime

from ..schemas import (
    AssignmentCreateRequest,
    AssignmentDeleteRequest,
    AssignmentResponse,
    MessageResponse
)
from ..middleware import get_current_user, RoleChecker, AuthUser
from ..database import get_supabase_admin_client
from ..utils.cache import cache

router = APIRouter(prefix="/api/assignments", tags=["Assignments"])


@router.post("", response_model=AssignmentResponse, dependencies=[Depends(RoleChecker(["admin"]))])
async def assign_teams(
    assignment_data: AssignmentCreateRequest,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Assign teams to a mentor (admin only).
    
    Creates mentor-team assignments and updates team mentor_id.
    """
    supabase = get_supabase_admin_client()
    
    # Verify mentor exists
    mentor_response = supabase.table("users").select("id, email, full_name, role, is_mentor").eq(
        "id", str(assignment_data.mentor_id)
    ).or_("role.eq.mentor,is_mentor.eq.true").execute()
    
    if not mentor_response.data:
        raise HTTPException(status_code=404, detail="Mentor not found")
    
    mentor = mentor_response.data[0]
    
    # Verify all teams exist and get their batch_ids
    team_ids_str = [str(tid) for tid in assignment_data.team_ids]
    teams_response = supabase.table("teams").select("id, team_name, batch_id").in_(
        "id", team_ids_str
    ).execute()
    
    if not teams_response.data or len(teams_response.data) != len(assignment_data.team_ids):
        found_ids = {team["id"] for team in teams_response.data} if teams_response.data else set()
        missing_ids = set(team_ids_str) - found_ids
        raise HTTPException(
            status_code=404,
            detail=f"Teams not found: {', '.join(missing_ids)}"
        )
    
    teams = teams_response.data
    
    # Bulk-update all teams with mentor_id in one query
    supabase.table("teams").update({
        "mentor_id": str(assignment_data.mentor_id)
    }).in_("id", team_ids_str).execute()
    
    # Batch existence check for assignments, then single bulk insert
    existing_resp = supabase.table("mentor_team_assignments").select("team_id")\
        .eq("mentor_id", str(assignment_data.mentor_id))\
        .in_("team_id", team_ids_str).execute()
    existing_ids = {r["team_id"] for r in existing_resp.data or []}

    new_records = [
        {
            "mentor_id": str(assignment_data.mentor_id),
            "team_id": team["id"],
            "batch_id": team["batch_id"],
            "assigned_by": str(current_user.user_id)
        }
        for team in teams if team["id"] not in existing_ids
    ]
    assignments = []
    if new_records:
        insert_resp = supabase.table("mentor_team_assignments").insert(new_records).execute()
        for a in insert_resp.data or []:
            assignments.append({
                "id": a["id"],
                "mentor_id": a["mentor_id"],
                "team_id": a["team_id"],
                "batch_id": a["batch_id"],
                "assigned_at": a["assigned_at"]
            })
    
    # Clear mentor's cache so dashboard updates immediately
    mentor_id_str = str(assignment_data.mentor_id)
    cache_keys_to_clear = [
        f"hackeval:mentor:team_ids:{mentor_id_str}",
        f"hackeval:mentor:dashboard:{mentor_id_str}",
        f"hackeval:mentor:reports:{mentor_id_str}:all"
    ]
    for key in cache_keys_to_clear:
        try:
            cache.delete(key)
            print(f"[Assignments] Cleared cache key: {key}")
        except Exception as e:
            print(f"[Assignments] Failed to clear cache key {key}: {e}")
    
    # Clear global mentor lookup cache so teams list shows updated mentor names
    try:
        cache.delete("hackeval:mentors:lookup")
        print("[Assignments] Cleared global mentor lookup cache")
    except Exception as e:
        print(f"[Assignments] Failed to clear mentor lookup cache: {e}")
    
    return AssignmentResponse(
        success=True,
        message=f"{len(assignment_data.team_ids)} teams assigned to {mentor.get('full_name', mentor['email'])}",
        assignments=assignments
    )


@router.delete("", response_model=MessageResponse, dependencies=[Depends(RoleChecker(["admin"]))])
async def unassign_teams(
    assignment_data: AssignmentDeleteRequest,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Unassign teams from a mentor (admin only).
    
    Removes mentor-team assignments and clears team mentor_id.
    """
    supabase = get_supabase_admin_client()
    
    # Verify mentor exists
    mentor_response = supabase.table("users").select("id, role, is_mentor").eq(
        "id", str(assignment_data.mentor_id)
    ).or_("role.eq.mentor,is_mentor.eq.true").execute()
    
    if not mentor_response.data:
        raise HTTPException(status_code=404, detail="Mentor not found")
    
    # Convert team IDs to strings
    team_ids_str = [str(tid) for tid in assignment_data.team_ids]
    
    # Bulk-clear mentor_id from teams and bulk-delete assignment records
    supabase.table("teams").update({"mentor_id": None})\
        .in_("id", team_ids_str)\
        .eq("mentor_id", str(assignment_data.mentor_id)).execute()

    supabase.table("mentor_team_assignments").delete()\
        .eq("mentor_id", str(assignment_data.mentor_id))\
        .in_("team_id", team_ids_str).execute()
    
    # Clear mentor's cache so dashboard updates immediately
    mentor_id_str = str(assignment_data.mentor_id)
    cache_keys_to_clear = [
        f"hackeval:mentor:team_ids:{mentor_id_str}",
        f"hackeval:mentor:dashboard:{mentor_id_str}",
        f"hackeval:mentor:reports:{mentor_id_str}:all"
    ]
    for key in cache_keys_to_clear:
        try:
            cache.delete(key)
            print(f"[Assignments] Cleared cache key: {key}")
        except Exception as e:
            print(f"[Assignments] Failed to clear cache key {key}: {e}")
    
    return MessageResponse(
        success=True,
        message=f"{len(assignment_data.team_ids)} teams unassigned from mentor"
    )


_HONORIFICS = {"dr.", "dr", "prof.", "prof", "mr.", "mr", "ms.", "ms", "mrs.", "mrs", "shri", "smt.", "smt", "er.", "er", "col.", "col"}

def _normalize_name(name: str) -> str:
    """Strip common honorific prefixes and normalise whitespace for fuzzy matching."""
    parts = name.lower().strip().split()
    while parts and parts[0] in _HONORIFICS:
        parts.pop(0)
    return " ".join(parts)


def _find_mentor(candidate: str, mentor_lookup: dict, norm_lookup: dict):
    """
    Try to find a mentor by candidate string (name or email).
    Matching order:
      1. Exact email/full_name match
      2. Honorific-stripped name exact match
      3. Substring partial match on original keys
      4. Substring partial match on normalized keys
    """
    if not candidate:
        return None
    c_lower = candidate.lower().strip()
    c_norm = _normalize_name(candidate)

    # 1. Exact match
    if c_lower in mentor_lookup:
        return mentor_lookup[c_lower]

    # 2. Normalized exact match (strips "Dr.", "Prof.", etc.)
    if c_norm and c_norm in norm_lookup:
        return norm_lookup[c_norm]

    # 3. Partial substring match on original keys
    for key, m in mentor_lookup.items():
        if c_lower in key or key in c_lower:
            return m

    # 4. Partial substring match on normalized keys
    if c_norm:
        for key, m in norm_lookup.items():
            if c_norm in key or key in c_norm:
                return m

    return None


@router.post("/auto-assign/{batch_id}", response_model=dict, dependencies=[Depends(RoleChecker(["admin"]))])
async def auto_assign_mentors(
    batch_id: UUID,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Automatically assign all unassigned teams in a batch to their designated mentors (admin only).

    Teams are matched to their designated mentor using metadata.suggested_mentor and
    metadata.ingestion.mentor (either field may hold a name or email). Matching is
    case-insensitive and will strip common honorific prefixes (Dr., Prof., Mr., etc.)
    before comparing so that "Dr. Rammanohar Nisarg" matches a user registered as
    "Rammanohar Nisarg".
    """
    supabase = get_supabase_admin_client()

    # Get all available mentors
    mentors_response = supabase.table("users").select(
        "id, email, full_name, role, is_mentor"
    ).or_("role.eq.mentor,is_mentor.eq.true").execute()

    if not mentors_response.data or len(mentors_response.data) == 0:
        raise HTTPException(
            status_code=404,
            detail="No mentors available for assignment"
        )

    mentors = mentors_response.data

    # Build lookup tables: exact key → mentor, normalized-name key → mentor
    mentor_lookup: dict = {}
    norm_lookup: dict = {}
    for mentor in mentors:
        if mentor.get("email"):
            mentor_lookup[mentor["email"].lower().strip()] = mentor
        if mentor.get("full_name"):
            original_key = mentor["full_name"].lower().strip()
            mentor_lookup[original_key] = mentor
            norm_key = _normalize_name(mentor["full_name"])
            if norm_key:
                norm_lookup[norm_key] = mentor
    
    # Get all unassigned teams in the batch (with metadata)
    unassigned_teams_response = supabase.table("teams").select(
        "id, team_name, batch_id, metadata"
    ).eq("batch_id", str(batch_id)).is_("mentor_id", "null").execute()
    
    unassigned_teams = unassigned_teams_response.data or []
    
    if len(unassigned_teams) == 0:
        return {
            "success": True,
            "message": "No unassigned teams found in this batch",
            "assigned_count": 0,
            "unavailable_count": 0,
            "mentor_assignments": {},
            "unavailable_teams": []
        }
    
    # Track assignments and unavailable teams
    mentor_assignments = {mentor["id"]: [] for mentor in mentors}
    unavailable_teams = []
    assigned_count = 0
    
    # Assign teams to their designated mentors
    for team in unassigned_teams:
        team_metadata = team.get("metadata") or {}
        ingestion = team_metadata.get("ingestion") or {}

        # Candidate mentor identifiers — try suggested_mentor first, then
        # ingestion.mentor (raw name from CSV) and ingestion.mentor_email
        candidates = [
            team_metadata.get("suggested_mentor"),
            ingestion.get("mentor"),
            ingestion.get("mentor_email"),
        ]
        # Use the first non-empty candidate that resolves to a registered mentor
        mentor = None
        matched_candidate = None
        for candidate in candidates:
            if candidate:
                mentor = _find_mentor(str(candidate), mentor_lookup, norm_lookup)
                if mentor:
                    matched_candidate = candidate
                    break

        if not mentor:
            # Record the best candidate name for the diagnostic message
            best_candidate = next((c for c in candidates if c), None)
            unavailable_teams.append({
                "team_name": team["team_name"],
                "designated_mentor": best_candidate or "No mentor specified",
                "reason": "No designated mentor specified" if not best_candidate else "Designated mentor not found in system",
            })
            continue
        
        mentor_id = mentor["id"]
        
        # Update team with mentor_id
        supabase.table("teams").update({
            "mentor_id": mentor_id
        }).eq("id", team["id"]).execute()
        
        # Create assignment record
        assignment_insert = {
            "mentor_id": mentor_id,
            "team_id": team["id"],
            "batch_id": team["batch_id"],
            "assigned_by": str(current_user.user_id)
        }
        
        # Check if assignment already exists
        existing = supabase.table("mentor_team_assignments").select("id").eq(
            "mentor_id", mentor_id
        ).eq("team_id", team["id"]).execute()
        
        if not existing.data:
            supabase.table("mentor_team_assignments").insert(
                assignment_insert
            ).execute()
        
        mentor_assignments[mentor_id].append(team["team_name"])
        assigned_count += 1
    
    # Clear all mentors' caches
    for mentor in mentors:
        mentor_id_str = mentor["id"]
        cache_keys_to_clear = [
            f"hackeval:mentor:team_ids:{mentor_id_str}",
            f"hackeval:mentor:dashboard:{mentor_id_str}",
            f"hackeval:mentor:reports:{mentor_id_str}:all"
        ]
        for key in cache_keys_to_clear:
            try:
                cache.delete(key)
            except Exception as e:
                print(f"[Auto-Assign] Failed to clear cache key {key}: {e}")
    
    # Clear global mentor lookup cache so teams list shows updated mentor names
    try:
        cache.delete("hackeval:mentors:lookup")
        print("[Auto-Assign] Cleared global mentor lookup cache")
    except Exception as e:
        print(f"[Auto-Assign] Failed to clear mentor lookup cache: {e}")
    
    # Format response with mentor names
    formatted_assignments = {}
    for mentor in mentors:
        mentor_id = mentor["id"]
        if mentor_assignments[mentor_id]:
            mentor_name = mentor.get("full_name") or mentor["email"]
            formatted_assignments[mentor_name] = {
                "mentor_id": mentor_id,
                "teams": mentor_assignments[mentor_id],
                "count": len(mentor_assignments[mentor_id])
            }
    
    # Build response message
    message_parts = []
    if assigned_count > 0:
        message_parts.append(f"Successfully assigned {assigned_count} teams to their designated mentors")
    if unavailable_teams:
        message_parts.append(f"{len(unavailable_teams)} teams could not be assigned (mentor not available)")
    
    message = ". ".join(message_parts) if message_parts else "No teams were assigned"
    
    return {
        "success": True,
        "message": message,
        "assigned_count": assigned_count,
        "unavailable_count": len(unavailable_teams),
        "mentor_assignments": formatted_assignments,
        "unavailable_teams": unavailable_teams
    }


@router.get("/mentor/{mentor_id}", response_model=dict)
async def get_mentor_assignments(
    mentor_id: UUID,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Get all team assignments for a specific mentor.
    
    Mentors can view their own assignments, admins can view any mentor's assignments.
    """
    supabase = get_supabase_admin_client()
    
    # Check authorization
    if current_user.role != "admin" and str(current_user.user_id) != str(mentor_id):
        raise HTTPException(
            status_code=403,
            detail="Access denied: You can only view your own assignments"
        )
    
    # Get assignments
    assignments_response = supabase.table("mentor_team_assignments").select(
        """
        *,
        teams!inner(id, team_name, health_status, batches!inner(id, name))
        """
    ).eq("mentor_id", str(mentor_id)).execute()
    
    assignments_data = assignments_response.data or []
    
    # Format response
    assignments = []
    for assignment in assignments_data:
        team = assignment.get("teams", {})
        if isinstance(team, list):
            team = team[0] if team else {}
        
        batch = team.get("batches", {})
        if isinstance(batch, list):
            batch = batch[0] if batch else {}
        
        assignments.append({
            "id": assignment["id"],
            "team_id": assignment["team_id"],
            "team_name": team.get("team_name"),
            "batch_id": assignment["batch_id"],
            "batch_name": batch.get("name"),
            "health_status": team.get("health_status"),
            "assigned_at": assignment["assigned_at"]
        })
    
    return {
        "mentor_id": str(mentor_id),
        "assignments": assignments,
        "total": len(assignments)
    }
