"""
Mentor Dashboard Router
Dedicated API endpoints for mentor-only access.
All endpoints require mentor role and filter data by the logged-in mentor's assignments.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from time import perf_counter
import json

from ..middleware.auth import get_current_user, AuthUser
from ..database import get_supabase, get_supabase_admin_client
from ..crud import TeamCRUD
from ..utils.cache import cache, RedisCache
from ..utils.report_storage import ReportStorageManager
from ..schemas import (
    LeaderboardResponse,
    LeaderboardItem,
    MentorReportResponse
)
from uuid import UUID


router = APIRouter(prefix="/api/mentor", tags=["Mentor Dashboard"])


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


def require_mentor(current_user: AuthUser = Depends(get_current_user)) -> AuthUser:
    """Dependency to ensure user is a mentor."""
    if current_user.role.lower() != "mentor":
        # Allow admin users with is_mentor flag
        if current_user.role.lower() == "admin":
            try:
                admin_supabase = get_supabase_admin_client()
                mentor_flag = admin_supabase.table("users").select("is_mentor").eq("id", str(current_user.user_id)).limit(1).execute()
                if mentor_flag.data and mentor_flag.data[0].get("is_mentor"):
                    return current_user
            except Exception as e:
                print(f"[Mentor Dashboard] Mentor flag lookup failed: {e}")
        raise HTTPException(status_code=403, detail="Mentor access required")
    return current_user


@router.get("/dashboard")
async def get_mentor_dashboard(
    current_user: AuthUser = Depends(require_mentor),
    no_cache: bool = Query(False, description="Bypass cache")
):
    """
    Get mentor's dashboard summary.
    Returns overview of assigned teams, their statuses, and key metrics.
    """
    start_time = perf_counter()
    supabase = get_supabase()
    mentor_id = str(current_user.user_id)

    cache_key = f"hackeval:mentor:dashboard:{mentor_id}"
    if not no_cache:
        cached_response = cache.get(cache_key)
        if cached_response:
            return cached_response
    
    # Get assigned team IDs
    team_ids = TeamCRUD.get_mentor_team_ids(mentor_id)
    
    if not team_ids:
        empty_response = {
            "totalTeams": 0,
            "teamsOnTrack": 0,
            "teamsAtRisk": 0,
            "teamsCritical": 0,
            "averageScore": 0,
            "recentActivity": []
        }
        return empty_response
    
    # Fetch teams data directly (no more project joins)
    teams_response = supabase.table("teams").select(
        "id, team_name, batch_id, health_status, total_score"
    ).in_("id", team_ids).execute()
    
    teams = teams_response.data or []
    
    # Calculate stats
    on_track = 0
    at_risk = 0
    critical = 0
    scores = []
    
    for team in teams:
        health = team.get("health_status", "on_track")
        if health == "on_track":
            on_track += 1
        elif health == "at_risk":
            at_risk += 1
        elif health == "critical":
            critical += 1
        
        # Get score directly from team
        score = team.get("total_score") or 0
        if score > 0:
            scores.append(score)
    
    avg_score = sum(scores) / len(scores) if scores else 0
    
    response = {
        "totalTeams": len(teams),
        "teamsOnTrack": on_track,
        "teamsAtRisk": at_risk,
        "teamsCritical": critical,
        "averageScore": round(avg_score, 2),
        "recentActivity": []  # Can be extended to show recent commits, etc.
    }

    cache.set(cache_key, response, RedisCache.TTL_SHORT)
    print(f"[Mentor Dashboard] /dashboard completed in {perf_counter() - start_time:.3f}s")
    return response


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_mentor_leaderboard(
    sort_by: str = Query("total_score", description="Field to sort by"),
    order: str = Query("desc", description="Sort order (asc or desc)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    batch_id: Optional[str] = Query(None, description="Filter by batch ID"),
    current_user: AuthUser = Depends(require_mentor)
):
    """
    Get leaderboard for mentor's assigned teams only.
    """
    import math
    supabase = get_supabase()
    mentor_id = str(current_user.user_id)
    
    # Get assigned team IDs
    team_ids = TeamCRUD.get_mentor_team_ids(mentor_id)
    
    if not team_ids:
        return LeaderboardResponse(
            leaderboard=[],
            total=0,
            page=page,
            page_size=page_size
        )
    
    # Get team IDs for these teams
    teams_query = supabase.table("teams").select("id").in_("id", team_ids)
    if batch_id:
        teams_query = teams_query.eq("batch_id", batch_id)
    
    teams_result = teams_query.execute()
    filtered_team_ids = [t["id"] for t in teams_result.data]
    
    if not filtered_team_ids:
        return LeaderboardResponse(
            leaderboard=[],
            total=0,
            page=page,
            page_size=page_size
        )
    
    # Query teams directly (no more projects table)
    query = supabase.table("teams").select("*", count="exact").in_("id", filtered_team_ids)
    query = query.eq("status", "completed")
    query = query.not_.is_("total_score", "null")
    
    # Pagination
    start = (page - 1) * page_size
    end = start + page_size - 1
    
    # Sorting
    desc = (order.lower() == "desc")
    query = query.range(start, end).order(sort_by, desc=desc)
    
    result = query.execute()
    total = result.count if hasattr(result, 'count') else len(result.data)
    
    # Build response
    leaderboard_items = []
    for idx, team in enumerate(result.data):
        leaderboard_items.append(LeaderboardItem(
            rank=start + idx + 1,
            id=UUID(team["id"]),
            repo_url=team["repo_url"],
            team_name=team.get("team_name"),
            total_score=team.get("total_score", 0),
            originality_score=team.get("originality_score"),
            quality_score=team.get("quality_score"),
            security_score=team.get("security_score"),
            implementation_score=team.get("implementation_score"),
            verdict=team.get("verdict"),
            analyzed_at=team.get("analyzed_at")
        ))
    
    return LeaderboardResponse(
        leaderboard=leaderboard_items,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/reports")
async def get_mentor_reports(
    batch_id: Optional[str] = Query(None, description="Filter by batch ID"),
    no_cache: bool = Query(False, description="Bypass cache"),
    current_user: AuthUser = Depends(require_mentor)
):
    """
    Get aggregated report for mentor's assigned teams.
    """
    start_time = perf_counter()
    supabase = get_supabase()
    mentor_id = str(current_user.user_id)

    print(f"[Mentor Dashboard] /reports called for mentor_id={mentor_id}, email={current_user.email}, batch_id={batch_id}")

    cache_key = f"hackeval:mentor:reports:{mentor_id}:{batch_id or 'all'}"
    if not no_cache:
        cached_response = cache.get(cache_key)
        if cached_response:
            print(f"[Mentor Dashboard] Returning cached response")
            return cached_response
    
    # Get assigned team IDs
    team_ids = TeamCRUD.get_mentor_team_ids(mentor_id)
    print(f"[Mentor Dashboard] Found {len(team_ids)} team IDs: {team_ids}")
    
    if not team_ids:
        print(f"[Mentor Dashboard] No teams found for mentor {mentor_id}")
        return {
            "mentorId": mentor_id,
            "generatedAt": datetime.utcnow().isoformat(),
            "teams": [],
            "summary": {
                "totalTeams": 0,
                "averageScore": 0,
                "teamsOnTrack": 0,
                "teamsAtRisk": 0,
                "teamsCritical": 0
            }
        }
    
    # Fetch teams directly (no more project joins)
    query = supabase.table("teams").select(
        "id, team_name, batch_id, health_status, total_score, quality_score, security_score, last_analyzed_at, analyzed_at, created_at, repo_url, student_count, metadata, report_json"
    ).in_("id", team_ids)
    if batch_id:
        query = query.eq("batch_id", batch_id)
    
    teams_response = query.execute()
    teams = teams_response.data or []

    # Build a quick lookup of grading state per team so UI can switch between
    # first-time grading and mark editing.
    grading_map: Dict[str, bool] = {}
    if team_ids:
        students_for_teams = supabase.table("students").select("team_id, grading_details").in_("team_id", team_ids).execute()
        for student in students_for_teams.data or []:
            team_key = student.get("team_id")
            if not team_key:
                continue

            grading_details = student.get("grading_details") or {}
            if isinstance(grading_details, str):
                try:
                    grading_details = json.loads(grading_details)
                except Exception:
                    grading_details = {}

            if not isinstance(grading_details, dict) or not grading_details:
                continue

            has_any_grade = False
            for round_data in grading_details.values():
                if isinstance(round_data, dict) and round_data.get("grade") is not None:
                    has_any_grade = True
                    break

            if has_any_grade:
                grading_map[str(team_key)] = True
    
    # Process teams
    teams_data = []
    scores = []
    on_track = 0
    at_risk = 0
    critical = 0
    
    for team in teams:
        total_score = team.get("total_score") or 0
        quality_score = team.get("quality_score") or 0
        security_score = team.get("security_score") or 0
        metadata = team.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}

        report_json = ReportStorageManager.get_report_for_team(team)

        ingestion = metadata.get("ingestion", {}) if isinstance(metadata, dict) else {}
        judge = report_json.get("judge", {}) if isinstance(report_json, dict) else {}
        problem_statement = (ingestion.get("project_statement", "") or judge.get("description", "") or "").strip()

        if total_score > 0:
            scores.append(total_score)
        
        health = team.get("health_status", "on_track")
        if health == "on_track":
            on_track += 1
        elif health == "at_risk":
            at_risk += 1
        elif health == "critical":
            critical += 1
        
        project_profile = metadata.get("project_profile") or report_json.get("project_profile") or report_json.get("judge", {}).get("project_profile") or {}
        if not isinstance(project_profile, dict):
            project_profile = {}
        archetype = project_profile.get("archetype", "unknown")
        manual_archetype = project_profile.get("manual_archetype")
        if manual_archetype:
            archetype = manual_archetype
        
        archetype_map = {
            "chrome_extension": "Browser Extension",
            "web_app": "Web Application",
            "mobile_app": "Mobile Application",
            "backend_api": "Backend API",
            "ml_ai_pipeline": "ML/AI Pipeline",
            "iot_embedded": "IoT/Embedded System",
            "cli_tool": "CLI Tool",
            "desktop_app": "Desktop Application",
            "game": "Game",
            "unknown": "General Project",
        }
        project_type = archetype_map.get(archetype, "General Project")

        teams_data.append({
            "teamId": team["id"],
            "teamName": team.get("team_name"),
            "batchId": team.get("batch_id"),
            "totalScore": total_score,
            "qualityScore": quality_score,
            "securityScore": security_score,
            "healthStatus": health,
            "lastAnalyzed": team.get("last_analyzed_at") or team.get("analyzed_at") or team.get("created_at"),
            "repoUrl": team.get("repo_url"),
            "studentCount": team.get("student_count", 0),
            "problemStatement": problem_statement,
            "projectProfile": {
                "archetype": archetype,
                "confidence": project_profile.get("confidence", "low"),
                "source": project_profile.get("source", "none"),
                "manual_archetype": manual_archetype,
            },
            "projectType": project_type,
            "isGraded": grading_map.get(team["id"], False)
        })
    
    avg_score = sum(scores) / len(scores) if scores else 0
    
    response = {
        "mentorId": mentor_id,
        "generatedAt": datetime.utcnow().isoformat(),
        "teams": teams_data,
        "summary": {
            "totalTeams": len(teams),
            "averageScore": round(avg_score, 2),
            "teamsOnTrack": on_track,
            "teamsAtRisk": at_risk,
            "teamsCritical": critical
        }
    }

    cache.set(cache_key, response, RedisCache.TTL_SHORT)
    print(f"[Mentor Dashboard] /reports completed in {perf_counter() - start_time:.3f}s")
    return response


@router.get("/teams/{team_id}/report")
async def get_mentor_team_report(
    team_id: str = Path(..., description="Team ID"),
    current_user: AuthUser = Depends(require_mentor)
):
    """
    Get detailed report for a specific team.
    Mentor must be assigned to this team.
    """
    start_time = perf_counter()
    supabase = get_supabase()
    mentor_id = str(current_user.user_id)

    cache_key = f"hackeval:mentor:team_report:{mentor_id}:{team_id}"
    cached_response = cache.get(cache_key)
    if cached_response:
        return cached_response
    
    # Verify mentor is assigned to this team
    team_ids = TeamCRUD.get_mentor_team_ids(mentor_id)
    
    if team_id not in team_ids:
        raise HTTPException(
            status_code=403,
            detail="You are not assigned to this team"
        )
    
    # Get team directly (no more project joins)
    team_response = supabase.table("teams").select(
        "id, team_name, batch_id, repo_url, health_status, total_score, quality_score, security_score, originality_score, engineering_score, organization_score, documentation_score, last_analyzed_at, analyzed_at, created_at, verdict, ai_pros, ai_cons, metadata, report_json"
    ).eq("id", team_id).execute()
    
    if not team_response.data:
        raise HTTPException(status_code=404, detail="Team not found")
    
    team = team_response.data[0]

    metadata = team.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}

    report_json = ReportStorageManager.get_report_for_team(team)

    ingestion = metadata.get("ingestion", {}) if isinstance(metadata, dict) else {}
    judge = report_json.get("judge", {}) if isinstance(report_json, dict) else {}
    problem_statement = (ingestion.get("project_statement", "") or judge.get("description", "") or "").strip()
    
    # Get scores directly from team
    total_score = team.get("total_score") or 0
    quality_score = team.get("quality_score") or 0
    security_score = team.get("security_score") or 0
    originality_score = team.get("originality_score") or 0
    architecture_score = team.get("engineering_score") or team.get("organization_score") or 0
    documentation_score = team.get("documentation_score") or 0
    
    # Get students
    students_response = supabase.table("students").select(
        "id, name, email, github_username, grading_details"
    ).eq("team_id", team_id).execute()
    students = students_response.data or []

    report_individual_scores = report_json.get("individualStudentScores", []) if isinstance(report_json, dict) else []

    def _normalize_score_key(value: Any) -> str:
        return str(value or "").strip().lower()

    score_by_id = {}
    score_by_github = {}
    score_by_email = {}
    score_by_name = {}

    if isinstance(report_individual_scores, list):
        for entry in report_individual_scores:
            if not isinstance(entry, dict):
                continue

            final_score = entry.get("finalScore")
            if final_score is None:
                continue

            key_id = _normalize_score_key(entry.get("id"))
            key_github = _normalize_score_key(entry.get("github"))
            key_email = _normalize_score_key(entry.get("email"))
            key_name = _normalize_score_key(entry.get("name"))

            if key_id:
                score_by_id[key_id] = final_score
            if key_github:
                score_by_github[key_github] = final_score
            if key_email:
                score_by_email[key_email] = final_score
            if key_name:
                score_by_name[key_name] = final_score

    project_profile = metadata.get("project_profile") or report_json.get("project_profile") or report_json.get("judge", {}).get("project_profile") or {}
    if not isinstance(project_profile, dict):
        project_profile = {}
    archetype = project_profile.get("archetype", "unknown")
    manual_archetype = project_profile.get("manual_archetype")
    if manual_archetype:
        archetype = manual_archetype

    archetype_map = {
        "chrome_extension": "Browser Extension",
        "web_app": "Web Application",
        "mobile_app": "Mobile Application",
        "backend_api": "Backend API",
        "ml_ai_pipeline": "ML/AI Pipeline",
        "iot_embedded": "IoT/Embedded System",
        "cli_tool": "CLI Tool",
        "desktop_app": "Desktop Application",
        "game": "Game",
        "unknown": "General Project",
    }
    project_type = archetype_map.get(archetype, "General Project")
    
    response = {
        "teamId": team_id,
        "teamName": team.get("team_name"),
        "batchId": team.get("batch_id"),
        "repoUrl": team.get("repo_url"),
        "problemStatement": problem_statement,
        "generatedAt": datetime.utcnow().isoformat(),
        "analysis": {
            "totalScore": total_score,
            "qualityScore": quality_score,
            "securityScore": security_score,
            "originalityScore": originality_score,
            "architectureScore": architecture_score,
            "documentationScore": documentation_score
        },
        "aiSummary": {
            "verdict": team.get("verdict"),
            "pros": team.get("ai_pros"),
            "cons": team.get("ai_cons")
        },
        "projectProfile": {
            "archetype": archetype,
            "confidence": project_profile.get("confidence", "low"),
            "source": project_profile.get("source", "none"),
            "manual_archetype": manual_archetype,
        },
        "projectType": project_type,
        "students": [
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "email": s.get("email"),
                "githubUsername": s.get("github_username"),
                "gradingDetails": s.get("grading_details") or {},
                "reportIndividualScore": (
                    score_by_id.get(_normalize_score_key(s.get("id")))
                    or score_by_github.get(_normalize_score_key(s.get("github_username")))
                    or score_by_email.get(_normalize_score_key(s.get("email")))
                    or score_by_name.get(_normalize_score_key(s.get("name")))
                )
            }
            for s in students
        ],
        "healthStatus": team.get("health_status", "on_track"),
        "lastAnalyzedAt": team.get("last_analyzed_at") or team.get("analyzed_at") or team.get("created_at")
    }

    cache.set(cache_key, response, RedisCache.TTL_SHORT)
    print(f"[Mentor Dashboard] /teams/{team_id}/report completed in {perf_counter() - start_time:.3f}s")
    return response


@router.post("/cache/clear")
async def clear_mentor_cache(
    current_user: AuthUser = Depends(require_mentor)
):
    """
    Clear all cache entries for the current mentor.
    Useful for debugging or forcing fresh data.
    """
    mentor_id = str(current_user.user_id)
    
    # Clear all mentor-related cache keys
    cache_keys = [
        f"hackeval:mentor:dashboard:{mentor_id}",
        f"hackeval:mentor:reports:{mentor_id}:all",
        f"hackeval:mentor:team_ids:{mentor_id}",
    ]
    
    cleared_count = 0
    for key in cache_keys:
        try:
            cache.delete(key)
            cleared_count += 1
        except Exception as e:
            print(f"[Mentor Dashboard] Failed to clear cache key {key}: {e}")
    
    print(f"[Mentor Dashboard] Cleared {cleared_count} cache entries for mentor {mentor_id}")
    
    return {
        "success": True,
        "message": f"Cleared {cleared_count} cache entries",
        "mentor_id": mentor_id
    }


@router.get("/debug/info")
async def get_mentor_debug_info(
    current_user: AuthUser = Depends(require_mentor)
):
    """
    Get debug information for the current mentor.
    Shows user info, team assignments, and cache status.
    """
    mentor_id = str(current_user.user_id)
    supabase = get_supabase()
    
    # Get team IDs (bypassing cache)
    team_ids_direct = []
    team_ids_assignments = []
    
    try:
        t_direct = supabase.table("teams").select("id, team_name").eq("mentor_id", mentor_id).execute()
        team_ids_direct = t_direct.data or []
    except Exception as e:
        print(f"[Debug] Error fetching direct teams: {e}")
    
    try:
        assignments = supabase.table("mentor_team_assignments").select("team_id, teams(id, team_name)").eq("mentor_id", mentor_id).execute()
        team_ids_assignments = assignments.data or []
    except Exception as e:
        print(f"[Debug] Error fetching assignments: {e}")
    
    # Get cached team IDs
    cache_key = f"hackeval:mentor:team_ids:{mentor_id}"
    cached_team_ids = cache.get(cache_key)
    
    return {
        "user": {
            "id": mentor_id,
            "email": current_user.email,
            "role": current_user.role,
            "full_name": current_user.full_name
        },
        "teams_via_direct_column": {
            "count": len(team_ids_direct),
            "teams": team_ids_direct
        },
        "teams_via_assignments": {
            "count": len(team_ids_assignments),
            "assignments": team_ids_assignments
        },
        "cached_team_ids": {
            "exists": cached_team_ids is not None,
            "count": len(cached_team_ids) if cached_team_ids else 0,
            "ids": cached_team_ids
        },
        "total_unique_teams": len(set(
            [t["id"] for t in team_ids_direct] +
            [a["team_id"] for a in team_ids_assignments]
        ))
    }


# Grading schemas
from pydantic import BaseModel

class MentorStudentGradeInput(BaseModel):
    """Input for grading a single student (mentor only)"""
    student_id: str
    grading_details: Optional[Dict[str, Any]] = None


@router.put("/teams/{team_id}/grades")
async def grade_team_students(
    team_id: str = Path(..., description="Team ID"),
    grades: List[MentorStudentGradeInput] = [],
    current_user: AuthUser = Depends(require_mentor)
):
    """
    Grade students in a team (Mentor only).
    This endpoint is separate from admin grading to avoid conflicts.
    Mentors can only grade students in teams assigned to them.
    Grades are validated against the batch's mentor_max_marks setting.
    """
    supabase = get_supabase_admin_client()  # Changed from get_supabase() to bypass RLS
    mentor_id = str(current_user.user_id)
    
    # Verify mentor is assigned to this team
    team_ids = TeamCRUD.get_mentor_team_ids(mentor_id)
    
    if team_id not in team_ids:
        raise HTTPException(
            status_code=403,
            detail="You are not assigned to this team"
        )
    
    # Get mentor max marks and optional round-wise limits from the batch
    mentor_max_marks = 100
    round_limits = {}
    team_data = supabase.table("teams").select("batch_id").eq("id", team_id).execute()
    if team_data.data and team_data.data[0].get("batch_id"):
        mentor_max_marks, round_limits = _load_batch_round_limits(supabase, team_data.data[0]["batch_id"])
    
    # Verify all students belong to this team
    student_ids = [g.student_id for g in grades]
    if student_ids:
        students_check = supabase.table("students").select("id").eq("team_id", team_id).in_("id", student_ids).execute()
        found_ids = {s["id"] for s in students_check.data}
        if len(found_ids) != len(student_ids):
            raise HTTPException(status_code=400, detail="One or more students do not belong to this team")
    
    # Update grades
    updated_count = 0
    errors = []
    
    print(f"Received grades update request for team {team_id} with {len(grades)} students.")
    
    for grade in grades:
        try:
            print(f"Processing student {grade.student_id}. Data: {grade.dict()}")
            update_data = {}
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

                current_student = supabase.table("students").select("grading_details").eq("id", grade.student_id).execute()
                if current_student.data:
                    current_details = current_student.data[0].get("grading_details") or {}
                    # Merge dictionaries (shallow merge of rounds)
                    current_details.update(grade.grading_details)
                    update_data["grading_details"] = current_details

            if "grading_details" in update_data:
                try:
                    supabase.table("students").update({"grading_details": update_data["grading_details"]}).eq("id", grade.student_id).execute()
                    updated_count += 1
                except Exception as e:
                    print(f"Error updating grading_details for student {grade.student_id}: {e}")
                    errors.append(f"Failed to update grading_details: {str(e)}")
                    continue
        except Exception as e:
            print(f"Error processing student {grade.student_id}: {e}")
            errors.append(f"Unexpected error for student {grade.student_id}: {str(e)}")
    
    if errors:
        return {
            "success": False,
            "message": f"Updated {updated_count} students with errors: {'; '.join(errors)}"
        }
    
    return {
        "success": True,
        "message": f"Successfully graded {updated_count} students"
    }

