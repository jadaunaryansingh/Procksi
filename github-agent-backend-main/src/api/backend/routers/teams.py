"""
Team Management Router - Phase 2
Handles all team CRUD operations and team-related endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, BackgroundTasks
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime
import csv
import io
import json
import logging
import traceback

from ..schemas import (
    TeamResponse, TeamDetailResponse, TeamListResponse,
    TeamCreateRequest, TeamUpdateRequest,
    BulkUploadResponse, AnalysisJobResponse,
    MessageResponse, TeamAssignRequest, StudentGradeRequest
)
from ..middleware import get_current_user, RoleChecker, AuthUser
from ..database import get_supabase, get_supabase_admin_client
from ..utils.contributor_identity import merge_contributors_by_team_members
from ..utils.report_storage import ReportStorageManager

router = APIRouter(prefix="/api/teams", tags=["Teams"])
logger = logging.getLogger(__name__)

# Email validation utility
import re
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
HONORIFIC_PREFIXES = re.compile(r'^(?:mr|mrs|ms|miss|dr|prof|sir|madam|mx)\.?\s+', re.IGNORECASE)

def validate_email(email: str | None) -> tuple[str | None, str | None]:
    """
    Validate email format using basic regex.
    
    Args:
        email: Email string to validate (can be None)
    
    Returns:
        Tuple of (validated_email, error_message)
        - If valid: (email, None)
        - If invalid: (None, error_message)
        - If None/empty: (None, None)
    """
    if not email:
        return None, None
    
    email = email.strip()
    if not email:
        return None, None
    
    if not EMAIL_REGEX.match(email):
        return None, f"Invalid email format: {email}"
    
    return email, None


def normalize_person_name(name: str | None) -> str:
    """Normalize a person name for matching across honorific and spacing differences."""
    if not name:
        return ""

    normalized = str(name).strip().lower()
    normalized = HONORIFIC_PREFIXES.sub("", normalized)
    normalized = re.sub(r"[.,]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    parts = normalized.split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[-1]}"

    return normalized


def _load_batch_round_limits(supabase, batch_id: str) -> tuple[int, dict]:
    """Return default mentor max marks and optional per-round limits for a batch."""
    mentor_max_marks = 100
    round_limits: dict = {}

    if not batch_id:
        return mentor_max_marks, round_limits

    batch_resp = supabase.table("batches").select("mentor_max_marks, mentor_rounds").eq("id", batch_id).limit(1).execute()
    if not batch_resp.data:
        return mentor_max_marks, round_limits

    batch_data = batch_resp.data[0]
    mentor_max_marks = int(batch_data.get("mentor_max_marks") or 100)

    raw_rounds = batch_data.get("mentor_rounds")
    if isinstance(raw_rounds, list):
        for round_cfg in raw_rounds:
            if not isinstance(round_cfg, dict):
                continue
            round_id = str(round_cfg.get("id") or "").strip()
            marks_out_of = round_cfg.get("marks_out_of")
            if not round_id:
                continue
            try:
                marks_int = int(marks_out_of)
            except (TypeError, ValueError):
                continue
            if marks_int < 1:
                continue
            round_limits[round_id] = marks_int

    return mentor_max_marks, round_limits


def _validate_round_grades(grading_details: dict, round_limits: dict, default_max: int, student_id: str) -> list:
    """Validate mentor round grades against configured limits."""
    errors = []

    if not isinstance(grading_details, dict):
        return errors

    for round_key, round_data in grading_details.items():
        if not isinstance(round_data, dict) or round_data.get("grade") is None:
            continue

        max_allowed = round_limits.get(str(round_key))
        if max_allowed is None:
            if round_limits:
                errors.append(f"Student {student_id}: round '{round_key}' is not scheduled for this batch")
                continue
            max_allowed = default_max

        grade_val = round_data.get("grade")
        try:
            grade_num = float(grade_val)
        except (TypeError, ValueError):
            errors.append(f"Student {student_id}: grade '{grade_val}' is not a valid number")
            continue

        if not grade_num.is_integer():
            errors.append(f"Student {student_id}: grade {grade_num} must be a whole number")
            continue

        grade_num = int(grade_num)

        if grade_num < 0 or grade_num > max_allowed:
            errors.append(f"Student {student_id}: grade {grade_num} exceeds max allowed ({max_allowed}) for round '{round_key}'")

    return errors


def _normalize_team_repo_urls(repo_urls: Optional[list], primary_repo_url: Optional[str] = None) -> list[str]:
    """Normalize a list of GitHub repository URLs while preserving order and removing duplicates."""
    normalized_urls: list[str] = []
    seen = set()

    def add_url(value: Optional[str]) -> None:
        if value is None:
            return
        cleaned = str(value).strip()
        if not cleaned:
            return
        if 'github.com' not in cleaned.lower():
            raise HTTPException(status_code=400, detail='Only GitHub repositories are supported')
        if cleaned in seen:
            return
        seen.add(cleaned)
        normalized_urls.append(cleaned)

    add_url(primary_repo_url)

    if repo_urls:
        for repo_url in repo_urls:
            add_url(repo_url)

    return normalized_urls


def _extract_team_repo_urls(team_row: dict) -> list[str]:
    """Return the primary repo plus any additional repos stored in metadata."""
    metadata = team_row.get('metadata') or {}
    if not isinstance(metadata, dict):
        metadata = {}

    repo_urls = []
    if team_row.get('repo_url'):
        repo_urls.append(team_row.get('repo_url'))

    metadata_repo_urls = metadata.get('repo_urls') or metadata.get('additional_repo_urls') or []
    if isinstance(metadata_repo_urls, list):
        repo_urls.extend(metadata_repo_urls)

    return _normalize_team_repo_urls(repo_urls)

# Try to import Celery at module level - fail fast if broken
CELERY_AVAILABLE = False
CELERY_IMPORT_ERROR = None
try:
    from celery_worker import analyze_repository_task
    CELERY_AVAILABLE = True
    logger.info("✅ Celery worker module imported successfully")
except Exception as e:
    CELERY_IMPORT_ERROR = str(e)
    logger.error(f"❌ Failed to import Celery worker at startup: {e}")
    logger.error(traceback.format_exc())


@router.get("", response_model=TeamListResponse)
async def list_teams(
    batch_id: Optional[UUID] = Query(None, description="Filter by batch ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    mentor_id: Optional[UUID] = Query(None, description="Filter by assigned mentor"),
    search: Optional[str] = Query(None, description="Search by team name or repo URL"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort: str = Query("name", description="Sort field"),
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Get list of teams with filtering and pagination.
    
    - **Admin**: Can see all teams, requires batch_id parameter
    - **Mentor**: Only sees assigned teams
    """
    supabase = get_supabase_admin_client()
    
    # Build query (base fields only; related data fetched separately for this page)
    query = supabase.table("teams").select(
        "id, team_name, batch_id, mentor_id, status, health_status, last_activity, "
        "created_at, updated_at, repo_url, metadata, total_score, quality_score, "
        "security_score, analyzed_at, last_analyzed_at",
        count="exact"
    )
    
    # Role-based filtering
    if current_user.role == "mentor":
        # Mentors only see their assigned teams
        # USE mentor_team_assignments table instead of teams.mentor_id
        assignments = supabase.table("mentor_team_assignments")\
            .select("team_id")\
            .eq("mentor_id", str(current_user.user_id))\
            .execute()
        
        assigned_team_ids = [a["team_id"] for a in assignments.data] if assignments.data else []
        
        if not assigned_team_ids:
             query = query.eq("id", "00000000-0000-0000-0000-000000000000")
        else:
             query = query.in_("id", assigned_team_ids)
            
    else:
        # Admins with is_mentor can see their own assigned teams when no filters provided
        if not batch_id and not mentor_id:
            try:
                mentor_flag = supabase.table("users").select("is_mentor").eq("id", str(current_user.user_id)).limit(1).execute()
                if mentor_flag.data and mentor_flag.data[0].get("is_mentor"):
                    assignments = supabase.table("mentor_team_assignments")\
                        .select("team_id")\
                        .eq("mentor_id", str(current_user.user_id))\
                        .execute()

                    assigned_team_ids = [a["team_id"] for a in assignments.data] if assignments.data else []
                    if not assigned_team_ids:
                        query = query.eq("id", "00000000-0000-0000-0000-000000000000")
                    else:
                        query = query.in_("id", assigned_team_ids)
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="batch_id or mentor_id is required for admin users"
                    )
            except HTTPException:
                raise
            except Exception as e:
                print(f"[Teams API] Mentor flag lookup error: {e}")
                raise HTTPException(
                    status_code=400,
                    detail="batch_id or mentor_id is required for admin users"
                )
        else:
            # Admins: require either batch_id or mentor_id (for viewing mentor's teams)
            if mentor_id:
                # Admin viewing a specific mentor's teams - no batch_id required
                query = query.eq("mentor_id", str(mentor_id))
            elif batch_id:
                # Admin viewing teams in a batch
                query = query.eq("batch_id", str(batch_id))
            else:
                # If no filters provided, defaulting to empty or error?
                # Existing logic raised 400.
                raise HTTPException(
                    status_code=400,
                    detail="batch_id or mentor_id is required for admin users"
                )
    
    # Apply filters
    # Special handling for "unassigned" status - filter by mentor_id IS NULL
    if status == "unassigned":
        query = query.is_("mentor_id", "null")
    elif status:
        query = query.eq("status", status)
    
    # Apply mentor_id filter if batch_id was used (to filter within a batch)
    if batch_id and mentor_id:
        query = query.eq("mentor_id", str(mentor_id))
    
    if search:
        search_term = search.strip()
        query = query.or_(f"team_name.ilike.%{search_term}%,repo_url.ilike.%{search_term}%")
    
    # Apply sorting (map frontend field names to database columns)
    sort_field = sort
    if sort == "name" or sort == "-name":
        # Frontend uses "name" but database has "team_name"
        sort_field = sort.replace("name", "team_name")
    
    if sort_field.startswith("-"):
        query = query.order(sort_field[1:], desc=True)
    else:
        query = query.order(sort_field)
    
    # Apply pagination and execute — count="exact" returns the full filtered count on response.count
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)
    response = query.execute()

    teams = response.data or []
    total = response.count if (hasattr(response, "count") and response.count is not None) else len(teams)
    
    # Apply natural sorting for team_name if that's the sort field
    # This ensures "Team 1", "Team 2", ..., "Team 10" sort correctly
    if sort_field in ["team_name", "-team_name"]:
        import re
        def natural_sort_key(team):
            """Extract numbers from team_name for natural sorting"""
            name = team.get("team_name", "")
            # Extract all numbers from the string
            numbers = re.findall(r'\d+', name)
            if numbers:
                # Convert first number to int for sorting, keep rest of string
                return (int(numbers[0]), name)
            return (float('inf'), name)  # Teams without numbers go to end
        
        teams.sort(key=natural_sort_key, reverse=sort_field.startswith("-"))

    batch_ids = [team.get("batch_id") for team in teams if team.get("batch_id")]

    if batch_ids:
        batches_response = supabase.table("batches").select("id, name, semester, year").in_("id", batch_ids).execute()
        batch_map = {batch["id"]: batch for batch in (batches_response.data or [])}
    else:
        batch_map = {}

    for team in teams:
        batch = batch_map.get(team.get("batch_id"))
        if batch:
            team["batches"] = batch

    # Compute student_count from students table for the current page of teams.
    team_ids = [team.get("id") for team in teams if team.get("id")]
    if team_ids:
        students_response = supabase.table("students").select("team_id").in_("team_id", team_ids).execute()
        student_counts = {}
        for student in students_response.data or []:
            team_id = student.get("team_id")
            if team_id:
                student_counts[team_id] = student_counts.get(team_id, 0) + 1

        for team in teams:
            team_id = team.get("id")
            team["student_count"] = student_counts.get(team_id, 0)

    # OPTIMIZED: Batch fetch mentor names (was: fetching after teams query)
    # Use cache to avoid repeated mentor queries
    from src.api.backend.utils.cache import cache, RedisCache
    
    mentor_ids = {str(team.get("mentor_id")) for team in teams if team.get("mentor_id")}
    
    if mentor_ids:
        # Try cache first (mentors change rarely)
        cache_key = "hackeval:mentors:lookup"
        mentor_lookup = cache.get(cache_key)
        
        if not mentor_lookup:
            # Cache miss - fetch all mentors and cache
            admin_supabase = get_supabase_admin_client()
            all_mentors = admin_supabase.table("users").select(
                "id, full_name, email, role, is_mentor"
            ).or_("role.eq.mentor,is_mentor.eq.true").execute()
            
            mentor_lookup = {
                str(m["id"]): m.get("full_name") or m.get("email") 
                for m in all_mentors.data or []
            }
            # Cache for 1 hour (mentors don't change often)
            cache.set(cache_key, mentor_lookup, RedisCache.TTL_LONG)
        
        # Assign mentor names to teams
        for team in teams:
            mentor_id = str(team.get("mentor_id")) if team.get("mentor_id") else None
            team["mentor_name"] = mentor_lookup.get(mentor_id) if mentor_id else None
    else:
        # No mentors to look up
        for team in teams:
            team["mentor_name"] = None
    
    return TeamListResponse(
        teams=teams,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )


@router.post("", response_model=TeamResponse, dependencies=[Depends(RoleChecker(["admin"]))])
async def create_team(
    team_data: TeamCreateRequest,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Create a new team (admin only).
    
    Creates team with students. Analysis fields are stored directly in the team record.
    """
    supabase = get_supabase_admin_client()
    
    # Verify batch exists
    batch_response = supabase.table("batches").select("id").eq("id", str(team_data.batch_id)).execute()
    if not batch_response.data:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    team_id = str(uuid4())
    
    # Create team
    team_insert = {
        "id": team_id,
        "batch_id": str(team_data.batch_id),
        "team_name": team_data.name,
        "repo_url": team_data.repo_url,
        "health_status": "on_track",
        "status": "pending",
        "student_count": len(team_data.students) if team_data.students else 0
    }
    
    try:
        team_response = supabase.table("teams").insert(team_insert).execute()
    except Exception as e:
        # Handle unique constraint for (batch_id, team_name)
        msg = str(e)
        if "unique_team_in_batch" in msg or "duplicate key" in msg:
            raise HTTPException(status_code=409, detail="A team with this name already exists in the selected batch")
        raise
    
    if not team_response.data:
        raise HTTPException(status_code=500, detail="Failed to create team")
    
    team = team_response.data[0]
    
    # Auto-queue analysis if repo URL provided
    if team_data.repo_url:
        try:
            from src.api.backend.crud import AnalysisJobCRUD, TeamCRUD
            # Create analysis job
            job = AnalysisJobCRUD.create_job(UUID(team_id))
            job_id = job.get("id") if job else None

            # Update team status to queued
            TeamCRUD.update_team_status(UUID(team_id), "queued")

            # Try to enqueue Celery task if available
            try:
                from celery_worker import analyze_single_repository_task
                task = analyze_single_repository_task.delay(
                    team_id=team_id,  # Updated to use team_id parameter
                    job_id=str(job_id),
                    repo_url=team_data.repo_url,
                    team_name=team_data.name
                )
                supabase.table('analysis_jobs').update({
                    'metadata': {'celery_task_id': task.id}
                }).eq('id', str(job_id)).execute()
            except Exception as celery_error:
                print(f"⚠ Celery queueing failed for new team: {celery_error}")
        except Exception as analysis_error:
            print(f"⚠ Auto-analysis setup failed for new team: {analysis_error}")
    
    # Create students
    if team_data.students:
        students_insert = [
            {
                "team_id": team_id,
                "name": student.name,
                "email": student.email,
                "github_username": student.github_username
            }
            for student in team_data.students
        ]
        
        supabase.table("students").insert(students_insert).execute()
    
    # Fetch complete team data
    team_detail = supabase.table("teams").select(
        """
        *,
        batches(id, name, semester, year),
        students(*)
        """
    ).eq("id", team_id).execute()
    
    return TeamResponse(
        team=team_detail.data[0],
        message="Team created successfully"
    )


@router.delete("/clear-all", response_model=MessageResponse, dependencies=[Depends(RoleChecker(["admin"]))])
async def clear_all_teams(
    batch_id: UUID = Query(..., description="Batch ID to clear teams from"),
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Delete all teams and dependent data for a batch (admin only).
    
    This will:
    - Cancel any running Celery analysis tasks
    - Delete all teams in the batch
    - Delete all related data (analysis jobs, snapshots, issues, etc.)
    """
    try:
        from celery_app import celery_app
    except ImportError:
        celery_app = None
    
    supabase = get_supabase_admin_client()

    teams_response = supabase.table("teams").select("id").eq("batch_id", str(batch_id)).execute()
    teams_data = teams_response.data or []

    if not teams_data:
        return MessageResponse(success=True, message="No teams found for this batch")

    team_ids = [team.get("id") for team in teams_data if team.get("id")]

    if team_ids:
        # Cancel all running Celery tasks for these teams
        if celery_app:
            jobs_response = supabase.table("analysis_jobs")\
                .select("id, metadata")\
                .in_("team_id", team_ids)\
                .in_("status", ["queued", "running"])\
                .execute()
            
            for job in (jobs_response.data or []):
                metadata = job.get("metadata", {})
                celery_task_id = metadata.get("celery_task_id")
                
                if celery_task_id:
                    try:
                        celery_app.control.revoke(celery_task_id, terminate=True, signal='SIGKILL')
                    except Exception as e:
                        print(f"Failed to revoke task {celery_task_id}: {e}")
        
        # Delete related data (all tables now use team_id after migration)
        # Order matters: delete child records before parent records
        supabase.table("analysis_jobs").delete().in_("team_id", team_ids).execute()
        supabase.table("analysis_snapshots").delete().in_("team_id", team_ids).execute()
        supabase.table("issues").delete().in_("team_id", team_ids).execute()
        supabase.table("project_comments").delete().in_("team_id", team_ids).execute()
        supabase.table("tech_stack").delete().in_("team_id", team_ids).execute()
        supabase.table("team_members").delete().in_("team_id", team_ids).execute()
        supabase.table("mentor_team_assignments").delete().in_("team_id", team_ids).execute()
        supabase.table("students").delete().in_("team_id", team_ids).execute()

    # Delete teams
    supabase.table("teams").delete().eq("batch_id", str(batch_id)).execute()

    return MessageResponse(success=True, message=f"Deleted {len(team_ids)} teams and all related data for this batch")


@router.post("/{team_id}/assign", response_model=MessageResponse, dependencies=[Depends(RoleChecker(["admin"]))])
async def assign_team_to_mentor(
    team_id: UUID,
    assignment: TeamAssignRequest,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Assign a single team to a mentor (admin only).
    """
    supabase = get_supabase_admin_client()

    # Verify team exists
    team_response = supabase.table("teams").select("id, team_name, batch_id").eq("id", str(team_id)).execute()
    if not team_response.data:
        raise HTTPException(status_code=404, detail="Team not found")

    team = team_response.data[0]

    # Verify mentor exists
    mentor_response = supabase.table("users").select("id, email, full_name, role, is_mentor").eq(
        "id", str(assignment.mentor_id)
    ).execute()

    if not mentor_response.data:
        raise HTTPException(status_code=404, detail="Mentor not found")

    mentor = mentor_response.data[0]
    is_valid_mentor = mentor.get("role") == "mentor" or mentor.get("is_mentor") is True
    if not is_valid_mentor:
        raise HTTPException(status_code=404, detail="Mentor not found")

    # Update team mentor_id
    supabase.table("teams").update({
        "mentor_id": str(assignment.mentor_id)
    }).eq("id", str(team_id)).execute()

    # Create assignment record if missing
    existing = supabase.table("mentor_team_assignments").select("id").eq(
        "mentor_id", str(assignment.mentor_id)
    ).eq("team_id", str(team_id)).execute()

    if not existing.data:
        supabase.table("mentor_team_assignments").insert({
            "mentor_id": str(assignment.mentor_id),
            "team_id": str(team_id),
            "batch_id": team.get("batch_id"),
            "assigned_by": str(current_user.user_id)
        }).execute()

    mentor_name = mentor.get("full_name") or mentor.get("email") or "mentor"

    return MessageResponse(
        success=True,
        message=f"Assigned {team.get('team_name', 'team')} to {mentor_name}"
    )


@router.post("/bulk-import", response_model=BulkUploadResponse, dependencies=[Depends(RoleChecker(["admin"]))])
async def bulk_import_teams_with_mentors(
    file: UploadFile = File(...),
    batch_id: UUID = Query(..., description="Batch ID for all teams"),
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Bulk import teams with mentor assignment via CSV or Excel (admin only).
    
    Supported formats: .csv, .xlsx
    
    CSV Format (Option A - with mentor):
    team_name,repo_url,mentor_email
    Team Alpha,https://github.com/org/alpha,drsmith@university.edu
    
    CSV Format (Option B - without mentor):
    team_name,repo_url
    Team Alpha,https://github.com/org/alpha
    
    Excel Format:
    Columns: Team Number, Team Name, Project Name, Github Link, etc.
    Maps: Team Name -> team_name, Github Link -> repo_url
    """
    supabase = get_supabase_admin_client()
    
    # Verify batch exists
    batch_response = supabase.table("batches").select("id, start_date").eq("id", str(batch_id)).execute()
    if not batch_response.data:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    # Determine file type and parse accordingly
    contents = await file.read()
    
    # We will parse into a structured list of teams to handle the "one row per student" format
    # structure: { "team_identifier": { "team_name": str, "repo_url": str, "mentor_email": str, "students": [ {name, email, ...} ] } }
    teams_map = {}
    
    if file.filename.endswith('.xlsx') or file.filename.endswith('.xls'):
        # Parse Excel file
        import openpyxl
        from io import BytesIO
        
        wb = openpyxl.load_workbook(BytesIO(contents), data_only=True)
        ws = wb.active
        
        # Get headers from first row
        headers = [str(cell.value).strip() if cell.value else "" for cell in ws[1]]
        
        # Email column patterns (order matters - more specific first)
        EMAIL_PATTERNS = [
            'mail id',      # University format
            'email id',     # Common variation
            'student email', # Explicit format
            'e-mail',       # Hyphenated format
            'email'         # Generic fallback
        ]
        
        # Column Identification
        col_map = {}
        for i, header in enumerate(headers):
            h_lower = header.lower().strip()
            if 'team no' in h_lower:
                col_map['team_id'] = i
            elif 'member name' in h_lower or 'name' in h_lower:
                col_map['student_name'] = i
            elif 'github' in h_lower or 'repo' in h_lower:
                col_map['repo_url'] = i
            elif 'mentor' in h_lower:
                col_map['mentor_email'] = i
            elif any(pattern in h_lower for pattern in EMAIL_PATTERNS):
                col_map['student_email'] = i
                logger.info(f"Detected email column: '{header}' at index {i}")
            elif 'roll' in h_lower:
                col_map['roll_no'] = i
            elif 'project' in h_lower and 'statement' in h_lower:
                col_map['project_desc'] = i
            elif 'section' in h_lower:
                col_map['section'] = i
            elif 'contact' in h_lower:
                col_map['contact'] = i
        
        # Diagnostic logging for column detection
        logger.info(f"Column mapping detected: {col_map}")
        if 'student_email' in col_map:
            logger.info(f"Email column found at index {col_map['student_email']}")
        else:
            logger.warning("No email column detected in uploaded file")
        
        # Check if we have the minimum required columns for the NEW format
        is_student_wise_format = 'team_id' in col_map and 'student_name' in col_map
        
        if is_student_wise_format:
            # === NEW FORMAT LOGIC (Student-wise rows with merged cells) ===
            current_team_no = None
            current_repo_url = None
            current_mentor = None
            current_project_desc = None
            
            for row in ws.iter_rows(min_row=2, values_only=True):
                # helpers to safely get cell value
                def get_val(idx): return str(row[idx]).strip() if idx is not None and idx < len(row) and row[idx] is not None else None
                
                # Check for Team No (Primary Key for grouping)
                raw_team_no = get_val(col_map.get('team_id'))
                
                # Forward Fill Logic
                if raw_team_no:
                    current_team_no = raw_team_no
                    # When specific team row starts, grab the other team-level attributes
                    current_repo_url = get_val(col_map.get('repo_url'))
                    current_mentor = get_val(col_map.get('mentor_email'))
                    current_project_desc = get_val(col_map.get('project_desc'))
                
                # If we don't have a team number yet (e.g. leading empty rows), skip
                if not current_team_no:
                    continue
                    
                # Normalize Team Name
                # If "Team No" is "1.0", make it "Team 1"
                try:
                    if current_team_no.endswith('.0'):
                        team_display_name = f"Team {int(float(current_team_no))}"
                    else:
                        team_display_name = f"Team {current_team_no}"
                except:
                    team_display_name = f"Team {current_team_no}"

                # Initialize team in map if needed
                if current_team_no not in teams_map:
                    teams_map[current_team_no] = {
                        "team_name": team_display_name,
                        "repo_url": current_repo_url or "",
                        "mentor_id": None, # Will lookup later
                        "mentor_email": current_mentor,
                        "project_description": current_project_desc or f"Project for {team_display_name}",
                        "team_no": current_team_no,
                        "project_statement": current_project_desc,
                        "mentor_raw": current_mentor,
                        "github_repository": current_repo_url,
                        "students": []
                    }
                
                # Add Student
                s_name = get_val(col_map.get('student_name'))
                if s_name:
                    # Validate email before adding
                    raw_email = get_val(col_map.get('student_email'))
                    validated_email, email_error = validate_email(raw_email)
                    
                    if email_error:
                        logger.warning(f"Invalid email for student '{s_name}' in team {current_team_no}: {email_error}")
                    
                    teams_map[current_team_no]["students"].append({
                        "name": s_name,
                        "email": validated_email,  # Use validated email (None if invalid)
                        "roll_no": get_val(col_map.get('roll_no')),
                        "section": get_val(col_map.get('section')),
                        "contact": get_val(col_map.get('contact'))
                    })

        else:
            # === FALLBACK/OLD format logic (Team-wise rows) ===
            # Map column indices for old format
            team_name_col = None
            repo_url_col = None
            mentor_email_col = None
            student_emails_col = None
            
            for i, header in enumerate(headers):
                if header:
                    header_lower = str(header).lower().strip()
                    if 'team name' in header_lower or 'teamname' in header_lower:
                        team_name_col = i
                    elif 'github' in header_lower or 'repo' in header_lower or 'repository' in header_lower:
                        repo_url_col = i
                    elif 'mentor' in header_lower and 'email' in header_lower:
                        mentor_email_col = i
                    elif 'mail id' in header_lower or ('student' in header_lower and 'email' in header_lower):
                        student_emails_col = i

            if team_name_col is not None and repo_url_col is not None:
                 for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True)):
                     t_name = str(row[team_name_col]).strip() if row[team_name_col] else ""
                     if t_name:
                         t_id = f"row_{row_idx}" # temporary ID
                         teams_map[t_id] = {
                            "team_name": t_name,
                            "repo_url": str(row[repo_url_col]).strip() if row[repo_url_col] else "",
                            "mentor_email": str(row[mentor_email_col]).strip() if mentor_email_col is not None and row[mentor_email_col] else None,
                            "team_no": None,
                            "project_statement": None,
                            "mentor_raw": str(row[mentor_email_col]).strip() if mentor_email_col is not None and row[mentor_email_col] else None,
                            "github_repository": str(row[repo_url_col]).strip() if row[repo_url_col] else "",
                            "students": [] # Needs parsing from strings if present
                         }
                         # Old format parsing for students involved comma separated emails strings, 
                         # which we handle below in the loop mostly, but let's prep it here
                         stud_str = str(row[student_emails_col]).strip() if student_emails_col is not None and row[student_emails_col] else ""
                         if stud_str:
                             # Try to split by comma or newline
                             emails = [e.strip() for e in stud_str.replace('\n', ',').split(',') if e.strip()]
                             # We don't have names in this specific old format usually, or they were in team name
                             names = []
                             if '\n' in t_name:
                                 names = [n.strip() for n in t_name.split('\n') if n.strip()]
                             elif ',' in t_name:
                                 names = [n.strip() for n in t_name.split(',') if n.strip()]
                             else:
                                 names = [t_name] # One person team?
                             
                             # Zip them up best effort
                             for k in range(max(len(emails), len(names))):
                                 n = names[k] if k < len(names) else f"Student {k+1}"
                                 e = emails[k] if k < len(emails) else None
                                 # Validate email
                                 validated_email, email_error = validate_email(e)
                                 if email_error:
                                     logger.warning(f"Invalid email in old format for '{n}': {email_error}")
                                 teams_map[t_id]["students"].append({"name": n, "email": validated_email})

    else:
        # Parse CSV file (Assuming old format for now as CSV doesn't support merge/grouping easily without strict schema)
        csv_file = io.StringIO(contents.decode("utf-8"))
        csv_reader = csv.DictReader(csv_file)
        for row_idx, row in enumerate(csv_reader):
              t_name = row.get("team_name", "").strip()
              if t_name:
                  t_id = f"csv_{row_idx}"
                  teams_map[t_id] = {
                      "team_name": t_name,
                      "repo_url": row.get("repo_url", "").strip(),
                      "mentor_email": row.get("mentor_email", "").strip(),
                      "team_no": None,
                      "project_statement": row.get("project_statement", "").strip() if row.get("project_statement") else None,
                      "mentor_raw": row.get("mentor_email", "").strip() if row.get("mentor_email") else None,
                      "github_repository": row.get("repo_url", "").strip(),
                      "students": []
                  }
                  # Parse students from CSV string if needed (similar to above)
                  # ... (Existing logic was simpler, just creating directly. We adopt structure now)
                  # For backward compat, we might just assume the user uses the Excel for the complex stuff.
                  # Simple recreation of students:
                  s_emails = row.get("student_emails", "")
                  if s_emails:
                       emails = [e.strip() for e in s_emails.replace('\n', ',').split(',') if e.strip()]
                       for e in emails:
                           # Validate email
                           validated_email, email_error = validate_email(e)
                           if email_error:
                               logger.warning(f"Invalid email in CSV for team '{t_name}': {email_error}")
                           teams_map[t_id]["students"].append({"name": "Student", "email": validated_email})

    successful = 0
    failed = 0
    errors = []
    created_teams = []

    existing_team_rows = supabase.table("teams").select("id, team_name").eq(
        "batch_id", str(batch_id)
    ).execute()
    existing_team_map = {
        (row.get("team_name") or "").lower(): row
        for row in (existing_team_rows.data or [])
    }

    def _chunk(items, size=200):
        for i in range(0, len(items), size):
            yield items[i:i + size]

    teams_payload = []
    students_payload = []
    assignments_payload = []
    team_members_payload = []
    project_ids_for_members = []
    
    # Get all mentors for email mapping
    mentors_response = supabase.table("users").select("id, email, full_name, role, is_mentor").or_("role.eq.mentor,is_mentor.eq.true").execute()
    # Create a map that tries to match by Email OR Name
    mentor_map = {}
    for m in mentors_response.data:
        if m.get("email"):
            mentor_map[m["email"].lower()] = m["id"]
        if m.get("full_name"):
            mentor_name = normalize_person_name(m["full_name"])
            mentor_map[mentor_name] = m["id"]
            mentor_map[m["full_name"].lower()] = m["id"]

    # Fetch existing teams in this batch for idempotent imports
    existing_team_rows = supabase.table("teams").select("id, team_name").eq(
        "batch_id", str(batch_id)
    ).execute()
    existing_team_map = {
        (row.get("team_name") or "").lower(): row
        for row in (existing_team_rows.data or [])
    }

    def _chunk(items, size=200):
        for i in range(0, len(items), size):
            yield items[i:i + size]
    
    # Collect payloads for batch operations
    teams_payload = []
    assignments_payload = []
    students_payload = []
    team_members_payload = []
    project_ids_for_members = []

    # Iterate over the Grouped Teams and Insert
    for team_key, team_data in teams_map.items():
        try:
            # Validate
            if not team_data["team_name"]:
                raise ValueError("Team name is missing")
            if not team_data["repo_url"]:
                # Some teams might not have a repo yet? 
                # Strict requirement: "Repository URL is required" in original code.
                # If we want to allow empty, change here. Assuming required for now.
                pass 

            # Resolve Mentor
            mentor_id = None
            m_input = team_data.get("mentor_email")
            if m_input:
                m_input = m_input.lower().strip()
                mentor_id = mentor_map.get(m_input)
                normalized_input = normalize_person_name(m_input)
                if not mentor_id:
                    mentor_id = mentor_map.get(normalized_input)
                # Try partial match if not exact?
                if not mentor_id:
                     # fallback: try identifying by normalized first/last name from the map keys
                     for k, v in mentor_map.items():
                         normalized_key = normalize_person_name(k)
                         if normalized_key and (normalized_key == normalized_input or normalized_key in normalized_input or normalized_input in normalized_key):
                             mentor_id = v
                             break

            # Check if team already exists in batch
            existing_team = existing_team_map.get(team_data["team_name"].lower())
            is_existing = bool(existing_team)
            common_id = existing_team["id"] if is_existing else str(uuid4())
            
            # Prepare metadata with raw mentor info
            team_metadata = {}
            if team_data.get("mentor_email"):
                team_metadata["suggested_mentor"] = team_data.get("mentor_email")

            # Store raw ingestion columns for admin review and downstream use
            # Fallback: if project_statement is missing, use team_name
            project_statement = team_data.get("project_statement")
            if not project_statement:
                project_statement = team_data.get("team_name")
            team_metadata["ingestion"] = {
                "team_no": team_data.get("team_no"),
                "project_statement": project_statement,
                "mentor": team_data.get("mentor_raw") or team_data.get("mentor_email"),
                "github_repository": team_data.get("github_repository") or team_data.get("repo_url"),
                "students": [
                    {
                        "member_name": s.get("name"),
                        "roll_number": s.get("roll_no"),
                        "section": s.get("section"),
                        "email_id": s.get("email"),
                        "contact_number": s.get("contact")
                    }
                    for s in team_data.get("students", [])
                ]
            }

            team_id = common_id

            # Create or update Team
            team_payload = {
                "batch_id": str(batch_id),
                "team_name": team_data["team_name"],
                "repo_url": team_data.get("repo_url"),
                "mentor_id": mentor_id,
                "health_status": "on_track",
                "status": "pending",
                "student_count": len(team_data["students"]),
                "metadata": team_metadata
            }
            team_payload["id"] = team_id
            teams_payload.append(team_payload)
            
            # Create Mentor Assignment
            if mentor_id:
                assignments_payload.append({
                    "mentor_id": mentor_id,
                    "team_id": team_id,
                    "batch_id": str(batch_id)
                })

            # Create Students
            students_to_insert = []
            team_members_to_insert = []  # For analytics
            
            for s in team_data["students"]:
                s_name = s["name"] or "Unknown Student"
                
                # Grading details / Metadata
                details = {}
                if s.get("roll_no"): details["roll_no"] = s.get("roll_no")
                if s.get("section"): details["section"] = s.get("section")
                if s.get("contact"): details["contact"] = s.get("contact")

                # Student Record
                students_to_insert.append({
                    "team_id": team_id,
                    "name": s_name,
                    "email": s.get("email"),
                    "grading_details": details
                })
                
                # Team Member Record (for analytics aggregation)
                if team_data.get("repo_url"): # Only if project exists
                    team_members_to_insert.append({
                        "team_id": team_id,  # Using team_id after migration
                        "name": s_name,
                        "commits": 0,
                        "contribution_pct": 0.0
                    })

            if students_to_insert:
                students_payload.extend(students_to_insert)

            if team_members_to_insert:
                team_members_payload.extend(team_members_to_insert)
                project_ids_for_members.append(team_id)

            created_teams.append({
                "id": team_id,
                "team_name": team_data.get("team_name"),
                "repo_url": team_data.get("repo_url"),
                "mentor_id": mentor_id,
                "batch_id": str(batch_id)
            })
            successful += 1

        except Exception as e:
            failed += 1
            errors.append({
                "row": team_key,
                "teamName": team_data.get("team_name", "Unknown"),
                "error": str(e)
            })

    def _dedupe_by_key(items, key):
        import uuid
        deduped = {}
        for item in items:
            item_key = item.get(key)
            if not item_key:
                # Keep items without the key by using a unique identifier
                deduped[str(uuid.uuid4())] = item
                continue
            deduped[item_key] = item
        return list(deduped.values())

    teams_payload = _dedupe_by_key(teams_payload, "id")
    # Deduplicate students by (email, team_id) instead of just email
    # This allows students to be in multiple teams/batches
    seen_students = set()
    deduped_students = []
    for s in students_payload:
        student_key = (s.get("email"), s.get("team_id"))
        if student_key not in seen_students:
            seen_students.add(student_key)
            deduped_students.append(s)

    # Filter out students with blank names or emails
    filtered_students = [
        s for s in deduped_students 
        if s.get("name") and s.get("team_id")
    ]

    # Batch write teams
    try:
        if teams_payload:
            for chunk in _chunk(teams_payload, 200):
                supabase.table("teams").upsert(chunk, on_conflict="id").execute()

        if assignments_payload:
            # Filter out existing mentor assignments in batch
            team_ids = [a["team_id"] for a in assignments_payload]
            mentor_ids = [a["mentor_id"] for a in assignments_payload]
            existing_assignments = supabase.table("mentor_team_assignments").select("mentor_id, team_id").in_(
                "team_id", team_ids
            ).in_("mentor_id", mentor_ids).execute()
            existing_pairs = {
                (row.get("mentor_id"), row.get("team_id")) for row in (existing_assignments.data or [])
            }
            pending = [a for a in assignments_payload if (a["mentor_id"], a["team_id"]) not in existing_pairs]
            for chunk in _chunk(pending, 200):
                supabase.table("mentor_team_assignments").insert(chunk).execute()

        if students_payload:
            for chunk in _chunk(filtered_students, 500):
                supabase.table("students").upsert(chunk, on_conflict="email,team_id").execute()

        if team_members_payload and project_ids_for_members:
            supabase.table("team_members").delete().in_("team_id", list(set(project_ids_for_members))).execute()
            for chunk in _chunk(team_members_payload, 500):
                supabase.table("team_members").insert(chunk).execute()
    except Exception as batch_error:
        failed += 1
        errors.append({
            "row": "bulk",
            "teamName": "batch",
            "error": f"Batch write failed: {str(batch_error)}"
        })

    return BulkUploadResponse(
        successful=successful,
        failed=failed,
        total=successful + failed,
        errors=errors,
        teams=created_teams, # Note: Returning partial objects here, might need schema adjustment if strict
        message=f"Bulk import completed: {successful} groups processed, {failed} failed"
    )


@router.post("/batch-upload", response_model=BulkUploadResponse, dependencies=[Depends(RoleChecker(["admin"]))])
async def bulk_upload_teams(
    file: UploadFile = File(...),
    batch_id: UUID = Query(..., description="Batch ID for all teams"),
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Bulk upload teams via CSV (admin only).
    
    CSV Format:
    teamName,repoUrl,description,student1Name,student1Email,student2Name,student2Email,...
    """
    supabase = get_supabase_admin_client()
    
    # Verify batch exists
    batch_response = supabase.table("batches").select("id").eq("id", str(batch_id)).execute()
    if not batch_response.data:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    # Read CSV
    contents = await file.read()
    csv_file = io.StringIO(contents.decode("utf-8"))
    csv_reader = csv.DictReader(csv_file)
    
    successful = 0
    failed = 0
    errors = []
    created_teams = []
    
    for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 (header is row 1)
        try:
            team_name = row.get("teamName", "").strip()
            repo_url = row.get("repoUrl", "").strip()
            description = row.get("description", "").strip()
            
            if not team_name:
                raise ValueError("Team name is required")
            
            # Extract students (up to 6 students)
            students = []
            for i in range(1, 7):
                student_name = row.get(f"student{i}Name", "").strip()
                student_email = row.get(f"student{i}Email", "").strip()
                
                if student_name:
                    students.append({
                        "name": student_name,
                        "email": student_email if student_email else None
                    })
            
            existing_team = existing_team_map.get(team_name.lower())
            team_id = existing_team["id"] if existing_team else str(uuid4())

            team_payload = {
                "id": team_id,
                "batch_id": str(batch_id),
                "team_name": team_name,
                "repo_url": repo_url,
                "health_status": "on_track",
                "status": "pending",
                "student_count": len(students)
            }
            teams_payload.append(team_payload)
            
            if students:
                students_payload.extend([
                    {
                        "team_id": team_id,
                        "name": s["name"],
                        "email": s["email"]
                    }
                    for s in students
                ])
            
            created_teams.append({
                "id": team_id,
                "team_name": team_name,
                "repo_url": repo_url,
                "batch_id": str(batch_id)
            })
            successful += 1
            
        except Exception as e:
            failed += 1
            errors.append({
                "row": row_num,
                "teamName": row.get("teamName", ""),
                "error": str(e)
            })
    
    def _dedupe_by_key(items, key):
        import uuid
        deduped = {}
        for item in items:
            item_key = item.get(key)
            if not item_key:
                deduped[str(uuid.uuid4())] = item
                continue
            deduped[item_key] = item
        return list(deduped.values())

    teams_payload = _dedupe_by_key(teams_payload, "id")
    students_payload = _dedupe_by_key(students_payload, "email")

    try:
        if teams_payload:
            for chunk in _chunk(teams_payload, 200):
                supabase.table("teams").upsert(chunk, on_conflict="id").execute()

        if students_payload:
            for chunk in _chunk(students_payload, 500):
                supabase.table("students").upsert(chunk, on_conflict="email").execute()
    except Exception as batch_error:
        failed += 1
        errors.append({
            "row": "bulk",
            "teamName": "batch",
            "error": f"Batch write failed: {str(batch_error)}"
        })

    return BulkUploadResponse(
        successful=successful,
        failed=failed,
        total=successful + failed,
        errors=errors,
        teams=created_teams,
        message=f"Batch upload completed: {successful} successful, {failed} failed"
    )


@router.get("/{team_id}")
async def get_team(
    team_id: UUID,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Get detailed team information.
    
    Returns complete team data including students, analysis results, team members, and health status.
    Frontend expects: team_name, repo_url, batches, analysis fields
    """
    supabase = get_supabase_admin_client()
    
    # Fetch team with all related data in a single query
    team_response = supabase.table("teams").select(
        """
        *,
        batches(id, name, semester, year),
        students(*),
        team_members(*)
        """
    ).eq("id", str(team_id)).execute()
    
    if not team_response.data:
        raise HTTPException(status_code=404, detail="Team not found")
    
    team = team_response.data[0]
    
    # Check authorization
    if current_user.role == "mentor":
        mentor_id = str(current_user.user_id)
        if team.get("mentor_id") != mentor_id:
            assignment = supabase.table("mentor_team_assignments").select("id").eq(
                "mentor_id", mentor_id
            ).eq("team_id", str(team_id)).limit(1).execute()
            if not assignment.data:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied: You are not assigned to this team"
                )
    
    # team_members is already embedded via the join above
    if "team_members" not in team or team["team_members"] is None:
        team["team_members"] = []

    # Resolve contributor aliases (different usernames/casing) into canonical students.
    students = team.get("students", []) if isinstance(team.get("students"), list) else []
    student_identities = [
        {
            "name": s.get("name", "Unknown"),
            "email": s.get("email"),
            "github": s.get("github_username"),
            "student_id": s.get("id"),
        }
        for s in students
        if isinstance(s, dict)
    ]

    # OPTIMIZED: Fetch full report from storage if migrated
    # This keeps the teams table lean (no 300KB JSON) while preserving full data access
    report_path = team.get("report_path")
    report_json = {}
    
    if report_path:
        # Team has been migrated to storage - fetch full report
        try:
            report_json = ReportStorageManager.get_report_from_storage(report_path)
            logger.debug(f"Loaded report from storage: {report_path}")
        except Exception as e:
            logger.warning(f"Failed to load report from storage ({report_path}): {e}")
            # Fallback to database report_json if storage fails
            report_json = team.get("report_json", {})
    else:
        # Team not yet migrated - use database report_json
        report_json = team.get("report_json", {})
    
    if isinstance(report_json, str):
        try:
            report_json = json.loads(report_json)
        except Exception:
            report_json = {}

    forensics = report_json.get("forensics", {}) if isinstance(report_json, dict) else {}
    author_stats_raw = forensics.get("author_stats", {}) if isinstance(forensics, dict) else {}

    if isinstance(author_stats_raw, dict):
        author_stats = [
            {"author": name, **data} if isinstance(data, dict) else {"author": name}
            for name, data in author_stats_raw.items()
        ]
    elif isinstance(author_stats_raw, list):
        author_stats = [item for item in author_stats_raw if isinstance(item, dict)]
    else:
        author_stats = []

    merged_members = merge_contributors_by_team_members(author_stats, student_identities)

    # If report author stats are missing, still normalize existing team_members payload.
    if not merged_members and isinstance(team.get("team_members"), list):
        team_members_raw = [
            {
                "author": m.get("name") or "Unknown",
                "email": m.get("email"),
                "commits": m.get("commits", m.get("commit_count", 0)) or 0,
            }
            for m in team.get("team_members", [])
            if isinstance(m, dict)
        ]
        merged_members = merge_contributors_by_team_members(team_members_raw, student_identities)

    total_member_commits = sum(max(int(m.get("commits", 0) or 0), 0) for m in merged_members)

    team["team_members"] = [
        {
            "id": (
                next(
                    (
                        s.get("student_id")
                        for s in student_identities
                        if str(s.get("name", "")).strip().lower()
                        == str((m.get("name") or m.get("author") or "")).strip().lower()
                    ),
                    None,
                )
                or f"member-{idx}-{str((m.get('name') or m.get('author') or 'unknown')).strip().lower().replace(' ', '-') }"
            ),
            "name": m.get("name") or m.get("author") or "Unknown",
            "commits": int(m.get("commits", m.get("commit_count", 0)) or 0),
            "contribution_pct": (
                round((int(m.get("commits", m.get("commit_count", 0)) or 0) / total_member_commits) * 100, 1)
                if total_member_commits > 0
                else 0
            ),
        }
        for idx, m in enumerate(merged_members)
    ]
    
    # Ensure batches is always an object (not None)
    if not team.get("batches"):
        team["batches"] = {
            "id": team["batch_id"],
            "name": "Unknown Batch",
            "semester": "",
            "year": 0
        }
    
    # Include full report_json in response (fetched from storage or DB)
    # This ensures frontend gets complete data regardless of storage location
    team["report_json"] = report_json
    
    return team


@router.put("/{team_id}", response_model=TeamResponse, dependencies=[Depends(RoleChecker(["admin"]))])
async def update_team(
    team_id: UUID,
    team_data: TeamUpdateRequest,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Update team details (admin only).
    
    Allows updating team name, description, status, and health status.
    """
    supabase = get_supabase_admin_client()
    
    # Check if team exists
    existing_team = supabase.table("teams").select(
        "id, batch_id, team_name, repo_url, metadata"
    ).eq("id", str(team_id)).execute()
    if not existing_team.data:
        raise HTTPException(status_code=404, detail="Team not found")
    team_row = existing_team.data[0]
    
    # Build update data
    update_data = {}
    if team_data.name is not None:
        update_data["team_name"] = team_data.name
    if team_data.status is not None:
        update_data["status"] = team_data.status
    if team_data.health_status is not None:
        update_data["health_status"] = team_data.health_status
    if team_data.risk_flags is not None:
        update_data["risk_flags"] = team_data.risk_flags
    if team_data.repo_urls is not None:
        normalized_repo_urls = _normalize_team_repo_urls(team_data.repo_urls, team_data.repo_url)
        update_data["repo_url"] = normalized_repo_urls[0] if normalized_repo_urls else None

        metadata = team_row.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        metadata["repo_urls"] = normalized_repo_urls
        update_data["metadata"] = metadata
    elif team_data.repo_url is not None:
        normalized_primary_repo = str(team_data.repo_url).strip() or None
        update_data["repo_url"] = normalized_primary_repo

        metadata = team_row.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        existing_repo_urls = _extract_team_repo_urls(team_row)
        if normalized_primary_repo:
            remaining_repos = [url for url in existing_repo_urls if url != team_row.get("repo_url")]
            metadata["repo_urls"] = _normalize_team_repo_urls(remaining_repos, normalized_primary_repo)
        elif existing_repo_urls:
            metadata["repo_urls"] = [url for url in existing_repo_urls if url != team_row.get("repo_url")]

        update_data["metadata"] = metadata
    if team_data.description is not None:
        update_data["description"] = team_data.description

        # Keep ingestion metadata in sync because frontend reads PS from metadata.ingestion.project_statement.
        metadata = team_row.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        ingestion = metadata.get("ingestion") or {}
        if not isinstance(ingestion, dict):
            ingestion = {}

        ingestion["project_statement"] = team_data.description
        metadata["ingestion"] = ingestion
        update_data["metadata"] = metadata
    
    # Update team
    if update_data:
        supabase.table("teams").update(update_data).eq("id", str(team_id)).execute()
    
    # Update students if provided
    if team_data.students:
        for student_update in team_data.students:
            student_data = {}
            if student_update.name is not None:
                student_data["name"] = student_update.name
            if student_update.email is not None:
                student_data["email"] = student_update.email
            if student_update.github_username is not None:
                student_data["github_username"] = student_update.github_username
            if student_data:
                # Verify student belongs to this team
                existing = supabase.table("students").select("id").eq(
                    "id", str(student_update.id)
                ).eq("team_id", str(team_id)).execute()
                if existing.data:
                    supabase.table("students").update(student_data).eq("id", str(student_update.id)).execute()
                else:
                    logger.warning(f"Student {student_update.id} not found in team {team_id}, skipping")
    
    # Add new students if provided
    if team_data.new_students:
        for new_student in team_data.new_students:
            insert_data = {
                "team_id": str(team_id),
                "name": new_student.name,
            }
            if new_student.email is not None:
                insert_data["email"] = new_student.email
            if new_student.github_username is not None:
                insert_data["github_username"] = new_student.github_username
            try:
                supabase.table("students").insert(insert_data).execute()
                logger.info(f"Added new student '{new_student.name}' to team {team_id}")
            except Exception as e:
                logger.error(f"Failed to add student '{new_student.name}' to team {team_id}: {e}")
    
    # Delete students if provided
    if team_data.delete_student_ids:
        for student_id in team_data.delete_student_ids:
            # Verify student belongs to this team before deleting
            existing = supabase.table("students").select("id").eq(
                "id", str(student_id)
            ).eq("team_id", str(team_id)).execute()
            if existing.data:
                supabase.table("students").delete().eq("id", str(student_id)).execute()
                logger.info(f"Deleted student {student_id} from team {team_id}")
            else:
                logger.warning(f"Student {student_id} not found in team {team_id}, skipping delete")
    
    # Fetch updated team
    updated_team = supabase.table("teams").select(
        """
        *,
        batches(id, name, semester, year),
        students(*)
        """
    ).eq("id", str(team_id)).execute()
    
    return TeamResponse(
        team=updated_team.data[0],
        message="Team updated successfully"
    )


@router.delete("/{team_id}", response_model=MessageResponse, dependencies=[Depends(RoleChecker(["admin"]))])
async def delete_team(
    team_id: UUID,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Delete a team and its associated data (admin only).
    
    Cascades to delete students and assignments.
    """
    supabase = get_supabase_admin_client()
    print(f"[Teams API] delete_team called for team_id={team_id}")
    
    # Check if team exists
    existing_team = supabase.table("teams").select("id").eq("id", str(team_id)).execute()
    if not existing_team.data:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Delete team (cascade will handle students and assignments)
    delete_response = supabase.table("teams").delete().eq("id", str(team_id)).execute()
    delete_error = getattr(delete_response, "error", None)
    if delete_error:
        raise HTTPException(status_code=500, detail=f"Failed to delete team: {delete_error}")
    
    return MessageResponse(
        success=True,
        message="Team deleted successfully"
    )


@router.get("/{team_id}/progress")
async def get_team_progress(
    team_id: UUID,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Get weekly progress snapshots for a team.
    
    Returns historical analysis data showing improvement over time.
    """
    supabase = get_supabase()
    
    # Verify team exists and check authorization
    team_response = supabase.table("teams").select(
        "id, team_name, batch_id, mentor_id"
    ).eq("id", str(team_id)).execute()
    
    if not team_response.data:
        raise HTTPException(status_code=404, detail="Team not found")
    
    team = team_response.data[0]
    
    # Check authorization
    if current_user.role == "mentor":
        mentor_id = str(current_user.user_id)
        if team.get("mentor_id") != mentor_id:
            assignment = supabase.table("mentor_team_assignments").select("id").eq(
                "mentor_id", mentor_id
            ).eq("team_id", str(team_id)).limit(1).execute()
            if not assignment.data:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied: You are not assigned to this team"
                )
    
    # Get all snapshots for this team
    snapshots_response = supabase.table("analysis_snapshots").select(
        """
        *,
        batch_analysis_runs(run_number, started_at, completed_at)
        """
    ).eq("team_id", str(team_id)).order("run_number", desc=False).execute()
    
    snapshots = snapshots_response.data or []
    
    # Calculate weekly trends
    weekly_data = []
    for snapshot in snapshots:
        run_info = snapshot.get("batch_analysis_runs", {})
        
        weekly_data.append({
            "week": snapshot["run_number"],
            "total_score": round(snapshot.get("total_score") or 0, 2),
            "originality_score": round(snapshot.get("originality_score") or 0, 2),
            "quality_score": round(snapshot.get("quality_score") or 0, 2),
            "security_score": round(snapshot.get("security_score") or 0, 2),
            "effort_score": round(snapshot.get("effort_score") or 0, 2),
            "commit_count": snapshot.get("commit_count", 0),
            "lines_of_code": snapshot.get("lines_of_code", 0),
            "analyzed_at": snapshot.get("analyzed_at"),
            "run_completed_at": run_info.get("completed_at") if isinstance(run_info, dict) else None
        })
    
    return weekly_data


@router.put("/{team_id}/grades", response_model=MessageResponse, dependencies=[Depends(RoleChecker(["admin", "mentor"]))])
async def update_student_grades(
    team_id: UUID,
    grades: List[StudentGradeRequest],
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Update grades for multiple students in a team.
    Allowed for Admins and the Assigned Mentor.
    Mentor grades are validated against the batch's mentor_max_marks setting.
    """
    supabase = get_supabase_admin_client()
    
    # Verify team exists
    team_response = supabase.table("teams").select("id, mentor_id, batch_id").eq("id", str(team_id)).execute()
    if not team_response.data:
        raise HTTPException(status_code=404, detail="Team not found")
    
    team = team_response.data[0]
    
    # Check permission
    if current_user.role == "mentor":
        mentor_id = str(current_user.user_id)
        if str(team.get("mentor_id")) != mentor_id:
            assignment = supabase.table("mentor_team_assignments").select("id").eq(
                "mentor_id", mentor_id
            ).eq("team_id", str(team_id)).limit(1).execute()
            if not assignment.data:
                raise HTTPException(status_code=403, detail="Not authorized to grade this team")
    
    # Get mentor max marks and optional round-wise limits from the batch
    mentor_max_marks, round_limits = _load_batch_round_limits(supabase, team.get("batch_id"))
    
    # Verify all students belong to this team
    student_ids = [str(g.student_id) for g in grades]
    students_check = supabase.table("students").select("id").eq("team_id", str(team_id)).in_("id", student_ids).execute()
    
    found_ids = {s["id"] for s in students_check.data}
    if len(found_ids) != len(student_ids):
        raise HTTPException(status_code=400, detail="One or more students do not belong to this team")

    errors = []
    updated_count = 0
    
    for grade in grades:
        try:
            update_data = {}
            if current_user.role == "admin":
                # Admin grading
                if grade.admin_grade is not None:
                    update_data["admin_grade"] = grade.admin_grade
                if grade.admin_feedback is not None:
                    update_data["admin_feedback"] = grade.admin_feedback
            else:
                # Mentor grading - validate against mentor_max_marks
                if grade.grading_details:
                    validation_errors = _validate_round_grades(
                        grade.grading_details,
                        round_limits,
                        mentor_max_marks,
                        str(grade.student_id),
                    )
                    if validation_errors:
                        errors.extend(validation_errors)
                        continue

                    current_student = supabase.table("students").select("grading_details").eq("id", str(grade.student_id)).execute()
                    if current_student.data:
                        current_details = current_student.data[0].get("grading_details") or {}
                        current_details.update(grade.grading_details)
                        update_data["grading_details"] = current_details
            
            
            if update_data:
                supabase.table("students").update(update_data).eq("id", str(grade.student_id)).execute()
                updated_count += 1
        except Exception as e:
            errors.append(f"Failed to update student {grade.student_id}: {str(e)}")
    
    if errors:
        return MessageResponse(success=False, message=f"Updated {updated_count} students with errors: {'; '.join(errors)}")
        
    return MessageResponse(success=True, message=f"Successfully graded {updated_count} students")


@router.put("/{team_id}/mentor-feedback", response_model=MessageResponse, dependencies=[Depends(RoleChecker(["admin", "mentor"]))])
async def update_mentor_feedback(
    team_id: UUID,
    body: dict,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Update general mentor feedback/suggestions for a team.
    Mentor can provide overall suggestions and the feedback is stored at the team level.
    """
    supabase = get_supabase_admin_client()
    
    team_response = supabase.table("teams").select("id, mentor_id").eq("id", str(team_id)).execute()
    if not team_response.data:
        raise HTTPException(status_code=404, detail="Team not found")
    
    team = team_response.data[0]
    
    # Check permission
    if current_user.role == "mentor":
        mentor_id = str(current_user.user_id)
        if str(team.get("mentor_id")) != mentor_id:
            assignment = supabase.table("mentor_team_assignments").select("id").eq(
                "mentor_id", mentor_id
            ).eq("team_id", str(team_id)).limit(1).execute()
            if not assignment.data:
                raise HTTPException(status_code=403, detail="Not authorized to provide feedback for this team")
    
    mentor_feedback = body.get("mentor_feedback", "")
    
    supabase.table("teams").update({
        "mentor_feedback": mentor_feedback
    }).eq("id", str(team_id)).execute()
    
    return MessageResponse(success=True, message="Mentor feedback updated successfully")

    # Calculate improvement from previous week
    improvement = 0
    if len(weekly_data) >= 2:
        latest = weekly_data[-1]
        previous = weekly_data[-2]
        improvement = latest["total_score"] - previous["total_score"]
    
    return {
        "team_id": str(team_id),
        "team_name": team["team_name"],
        "batch_id": team["batch_id"],
        "total_weeks": len(weekly_data),
        "current_score": weekly_data[-1]["total_score"] if weekly_data else 0,
        "improvement": round(improvement, 2),
        "weekly_data": weekly_data
    }


@router.post("/{team_id}/analyze", response_model=AnalysisJobResponse, dependencies=[Depends(RoleChecker(["admin"]))])
async def analyze_team(
    team_id: UUID,
    force: bool = Query(False, description="Force re-analysis (admin only)"),
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Trigger manual analysis for a team's repository (Admin only).
    
    Creates an analysis job and queues it for processing with Celery.
    
    Note: Only admins can manually trigger analysis. Mentors can view analysis
    results but cannot trigger new analyses. Automatic re-analysis is scheduled
    to run every 7 days via the batch analysis system.
    
    Use force=true to re-analyze immediately regardless of the last analysis time.
    
    Returns HTTP 503 if Celery is unavailable.
    """
    supabase = get_supabase_admin_client()
    
    # Check if Celery is available
    if not CELERY_AVAILABLE:
        logger.error(f"Celery unavailable, cannot queue analysis. Error: {CELERY_IMPORT_ERROR}")
        raise HTTPException(
            status_code=503,
            detail=f"Analysis service unavailable. Celery worker not accessible: {CELERY_IMPORT_ERROR}"
        )
    
    # Get team
    team_response = supabase.table("teams").select("*").eq("id", str(team_id)).execute()
    
    if not team_response.data:
        raise HTTPException(status_code=404, detail="Team not found")
    
    team = team_response.data[0]

    repo_urls = _extract_team_repo_urls(team)
    
    # Check if team has at least one repo URL (primary repo or additional repos)
    if not repo_urls:
        raise HTTPException(status_code=400, detail="Team has no repository URL")
    
    # For manual admin triggers, check if currently analyzing
    current_status = team.get("status")
    if current_status in ["analyzing", "queued"]:
        return AnalysisJobResponse(
            job_id=None,
            team_id=team_id,
            status="skipped",
            message=f"Analysis already in progress (status: {current_status})"
        )
    
    # Create a manual batch run so analysis shows in weekly progress charts
    batch_run_id = None
    run_number = None
    if team.get("batch_id"):
        try:
            last_run_result = supabase.table("batch_analysis_runs")\
                .select("run_number")\
                .eq("batch_id", str(team["batch_id"]))\
                .order("run_number", desc=True)\
                .limit(1)\
                .execute()

            run_number = 1
            if last_run_result.data:
                run_number = last_run_result.data[0]["run_number"] + 1

            run_insert = {
                "batch_id": str(team["batch_id"]),
                "run_number": run_number,
                "status": "running",
                "total_teams": 1,
                "completed_teams": 0,
                "failed_teams": 0,
                "started_at": datetime.now().isoformat(),
                "metadata": {
                    "trigger": "manual",
                    "team_id": str(team_id)
                }
            }

            run_result = supabase.table("batch_analysis_runs").insert(run_insert).execute()
            if run_result.data:
                batch_run_id = run_result.data[0]["id"]
        except Exception as run_error:
            logger.warning(f"⚠ Manual batch run creation failed: {run_error}")

    # Create analysis job
    job_insert = {
        "team_id": str(team_id),
        "status": "queued",
        "requested_by": str(current_user.user_id),
        "started_at": datetime.now().isoformat(),
        "batch_id": str(team.get("batch_id")) if team.get("batch_id") else None,
        "run_number": run_number,
        "metadata": {
            "trigger": "manual",
            "batch_run_id": batch_run_id,
            "run_number": run_number,
            "team_id": str(team_id)
        } if batch_run_id else {"trigger": "manual"}
    }
    
    job_response = supabase.table("analysis_jobs").insert(job_insert).execute()
    
    if not job_response.data:
        raise HTTPException(status_code=500, detail="Failed to create analysis job")
    
    job = job_response.data[0]
    job_id = job["id"]
    
    # Update team status to queued
    supabase.table("teams").update({
        "status": "queued"
    }).eq("id", str(team_id)).execute()
    
    # Queue Celery task SYNCHRONOUSLY (not in BackgroundTasks)
    # Use dedicated single_analysis queue for immediate processing
    try:
        logger.info(f"🚀 Queueing Celery task for team {team_id}, job {job_id}")
        
        # Import the single repository analysis task
        from celery_worker import analyze_single_repository_task
        
        task = analyze_single_repository_task.delay(
            team_id=str(team_id),
            job_id=str(job_id),
            repo_url=repo_urls[0],
            team_name=team.get("team_name")
        )
        
        # Verify task was queued successfully
        if not task or not task.id:
            raise Exception("Task queued but no task ID returned")
        
        logger.info(f"✅ Celery task queued successfully: {task.id} (single_analysis queue)")
        
        # Store celery_task_id in metadata
        updated_metadata = {**job.get('metadata', {}), 'celery_task_id': task.id, 'queue': 'single_analysis'}
        supabase.table('analysis_jobs').update({
            'metadata': updated_metadata
        }).eq('id', str(job_id)).execute()
        
        return AnalysisJobResponse(
            job_id=job_id,
            team_id=team_id,
            status="queued",
            message="Analysis queued successfully"
        )
        
    except Exception as e:
        # Celery queuing failed - update job status and return error
        error_msg = f"Failed to queue Celery task: {str(e)}"
        logger.error(f"❌ {error_msg}")
        logger.error(traceback.format_exc())
        
        # Update job status to failed
        supabase.table('analysis_jobs').update({
            'status': 'failed',
            'error_message': error_msg,
            'completed_at': datetime.now().isoformat()
        }).eq('id', str(job_id)).execute()
        
        # Update team status back to previous state
        supabase.table("teams").update({
            "status": "pending"
        }).eq("id", str(team_id)).execute()
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to queue analysis task: {str(e)}"
        )
