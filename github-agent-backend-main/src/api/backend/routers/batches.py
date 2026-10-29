"""
Batch Management Router
Handles CRUD operations for academic batches/semesters
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query, Request
from fastapi.responses import StreamingResponse
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime
from decimal import Decimal, InvalidOperation
import csv
import io
import os
import re
from pydantic import BaseModel, Field


_ILLEGAL_EXCEL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

from ..schemas import (
    BatchCreateRequest,
    BatchUpdateRequest,
    BatchResponse,
    BatchStatsResponse,
    BatchListResponse,
    ErrorResponse,
    MentorRoundCreateRequest,
    MentorRoundUpdateRequest,
    MentorRoundListResponse,
)
from ..middleware import get_current_user, AuthUser, RoleChecker
from ..database import get_supabase_admin_client
from ..utils.email import send_alert_email, EmailConfigError
from ..templates.email_templates import EmailTemplates

router = APIRouter(prefix="/api/batches", tags=["Batch Management"])


class MentorMarksReminderBulkRequest(BaseModel):
    team_ids: List[UUID] = Field(default_factory=list)


def _normalize_mentor_rounds(raw_rounds: Any) -> List[Dict[str, Any]]:
    """Normalize mentor rounds from JSONB into a safe response shape."""
    normalized: List[Dict[str, Any]] = []
    if not isinstance(raw_rounds, list):
        return normalized

    for item in raw_rounds:
        if not isinstance(item, dict):
            continue

        round_id = str(item.get("id") or "").strip()
        round_name = str(item.get("name") or "").strip()
        marks_raw = item.get("marks_out_of")

        if not round_id or not round_name:
            continue

        try:
            marks_out_of = int(marks_raw)
        except (TypeError, ValueError):
            continue

        if marks_out_of < 1:
            continue

        normalized.append({
            "id": round_id,
            "name": round_name,
            "marks_out_of": marks_out_of,
            "created_at": item.get("created_at"),
        })

    return normalized


def _extract_team_no(team_name: str) -> str:
    """Extract numeric team number from team name when possible."""
    value = str(team_name or "").strip()
    if not value:
        return ""

    match = re.search(r"\d+", value)
    if match:
        return match.group(0)
    return value


def _format_csv_mark(value: Any) -> str:
    """Format grade values for CSV without unnecessary trailing decimals."""
    if value is None:
        return ""

    text_value = str(value).strip()
    if not text_value:
        return ""

    try:
        decimal_value = Decimal(text_value)
    except (InvalidOperation, ValueError):
        return text_value

    normalized_value = decimal_value.normalize()
    if normalized_value == normalized_value.to_integral():
        return format(normalized_value.to_integral(), "f")

    return format(normalized_value, "f").rstrip("0").rstrip(".")


def _extract_round_rows(grading_details: Any, round_name_map: Dict[str, str]) -> List[Dict[str, str]]:
    """Return one row per round with separate marks and feedback values."""
    if not isinstance(grading_details, dict):
        return [{"round": "", "marks": "", "feedback": ""}]

    rows: List[Dict[str, str]] = []
    for round_id, round_data in grading_details.items():
        if not isinstance(round_data, dict):
            continue

        grade = round_data.get("grade")
        feedback = str(round_data.get("feedback") or "").strip()
        if grade is None and not feedback:
            continue

        rows.append({
            "round": round_name_map.get(str(round_id), str(round_id)),
            "marks": _format_csv_mark(grade),
            "feedback": feedback,
        })

    if not rows:
        rows.append({"round": "", "marks": "", "feedback": ""})

    return rows


def _has_round_data(round_data: Any) -> bool:
    """Return True when a round entry has a grade or non-empty feedback."""
    if not isinstance(round_data, dict):
        return False

    grade = round_data.get("grade")
    feedback = str(round_data.get("feedback") or "").strip()
    return grade is not None or bool(feedback)


def _extract_single_round_row(
    grading_details: Any,
    selected_round_id: Optional[str],
    round_name_map: Dict[str, str],
) -> Dict[str, str]:
    """Return CSV row fields for one selected round, or blank values when unavailable."""
    if not selected_round_id:
        return {"round": "", "marks": "", "feedback": ""}

    round_label = round_name_map.get(selected_round_id, selected_round_id)
    if not isinstance(grading_details, dict):
        return {"round": round_label, "marks": "", "feedback": ""}

    round_data = grading_details.get(selected_round_id)
    if not isinstance(round_data, dict):
        return {"round": round_label, "marks": "", "feedback": ""}

    grade = round_data.get("grade")
    feedback = str(round_data.get("feedback") or "").strip()
    return {
        "round": round_label,
        "marks": _format_csv_mark(grade),
        "feedback": feedback,
    }


def _parse_mark_as_float(mark_value: Any) -> Optional[float]:
    """Safely parse a mark into float for sorting and ranking."""
    if mark_value is None:
        return None

    text_value = str(mark_value).strip()
    if not text_value:
        return None

    try:
        return float(text_value)
    except (TypeError, ValueError):
        return None


def _is_missing_project_id_column_error(error: Exception) -> bool:
    """Detect Postgres undefined-column errors for teams.project_id."""
    error_code = str(getattr(error, "code", "") or "")
    error_text = str(error).lower()
    if error_code == "42703":
        return True
    return "teams.project_id" in error_text and "does not exist" in error_text


def _extract_student_profile_fields(grading_details: Any) -> Dict[str, str]:
    """Extract student profile fields stored alongside grading details."""
    if not isinstance(grading_details, dict):
        return {"roll_number": "", "section": "", "contact_number": ""}

    roll_number = str(
        grading_details.get("roll_no")
        or grading_details.get("roll_number")
        or ""
    ).strip()
    section = str(grading_details.get("section") or "").strip()
    contact_number = str(
        grading_details.get("contact")
        or grading_details.get("contact_number")
        or ""
    ).strip()

    return {
        "roll_number": roll_number,
        "section": section,
        "contact_number": contact_number,
    }


def _resolve_round_label(
    *,
    batch_rounds: List[Dict[str, Any]],
    round_id: Optional[str],
) -> str:
    """Resolve a display label for reminder emails and API payloads."""
    selected_round_id = str(round_id or "").strip()
    if not selected_round_id:
        return ""

    for round_cfg in batch_rounds:
        cfg_id = str(round_cfg.get("id") or "").strip()
        if cfg_id == selected_round_id:
            return str(round_cfg.get("name") or selected_round_id).strip() or selected_round_id

    return selected_round_id


def _build_mentor_dashboard_url(frontend_url_override: Optional[str] = None) -> str:
    """Build mentor dashboard URL used in notification emails."""
    frontend_url = str(frontend_url_override or os.getenv("FRONTEND_URL") or "").strip().rstrip("/")
    if not frontend_url:
        raise EmailConfigError(
            "Frontend dashboard URL is not configured. "
            "Set FRONTEND_URL in backend env or send requests from deployed frontend origin."
        )
    return f"{frontend_url}/mentor/dashboard"


def _notify_assigned_mentors_for_round(
    *,
    supabase,
    batch_id: UUID,
    batch_name: str,
    round_name: str,
    requested_by: str,
    frontend_url_override: Optional[str] = None,
) -> Dict[str, int]:
    """Send round-created email to mentors who have at least one assigned team in this batch."""
    teams_resp = (
        supabase
        .table("teams")
        .select("mentor_id")
        .eq("batch_id", str(batch_id))
        .execute()
    )

    mentor_team_counts: Dict[str, int] = {}
    for team in teams_resp.data or []:
        mentor_id = str(team.get("mentor_id") or "").strip()
        if not mentor_id:
            continue
        mentor_team_counts[mentor_id] = mentor_team_counts.get(mentor_id, 0) + 1

    if not mentor_team_counts:
        return {"attempted": 0, "sent": 0, "failed": 0}

    mentor_ids = list(mentor_team_counts.keys())
    mentors_resp = (
        supabase
        .table("users")
        .select("id, email, full_name")
        .in_("id", mentor_ids)
        .execute()
    )

    mentor_dashboard_url = _build_mentor_dashboard_url(frontend_url_override=frontend_url_override)
    attempted = 0
    sent = 0
    failed = 0

    for mentor in mentors_resp.data or []:
        mentor_id = str(mentor.get("id") or "").strip()
        mentor_email = str(mentor.get("email") or "").strip()
        if not mentor_id or not mentor_email:
            continue

        attempted += 1
        mentor_name = str(mentor.get("full_name") or "").strip() or "Mentor"
        team_count = mentor_team_counts.get(mentor_id, 0)

        try:
            subject = EmailTemplates.mentor_round_assignment_subject(
                batch_name=batch_name,
                round_name=round_name,
            )
            email_parts = EmailTemplates.mentor_round_assignment_body(
                mentor_name=mentor_name,
                batch_name=batch_name,
                round_name=round_name,
                team_count=team_count,
                dashboard_url=mentor_dashboard_url,
                requested_by=requested_by,
            )
            send_alert_email(
                subject=subject,
                body_text=email_parts["text"],
                html_body=email_parts["html"],
                to_email=mentor_email,
                use_mentor_sender=True,
            )
            sent += 1
        except Exception as e:
            failed += 1
            print(f"[Batches] Failed to send round notification to {mentor_email}: {e}")

    return {"attempted": attempted, "sent": sent, "failed": failed}


def _resolve_student_export_fields(student: Dict[str, Any], ingestion_students: List[Dict[str, Any]]) -> Dict[str, str]:
    """Resolve student export fields, preferring ingestion metadata over fallback details."""
    student_name = str(student.get("name") or "").strip()
    student_email = str(student.get("email") or "").strip()
    student_name_l = student_name.lower()
    student_email_l = student_email.lower()

    matched_ingestion: Dict[str, Any] = {}
    for entry in ingestion_students:
        if not isinstance(entry, dict):
            continue

        entry_name = str(entry.get("member_name") or "").strip().lower()
        entry_email = str(entry.get("email_id") or "").strip().lower()
        if student_email_l and entry_email == student_email_l:
            matched_ingestion = entry
            break
        if student_name_l and entry_name == student_name_l:
            matched_ingestion = entry
            break

    fallback_details = _extract_student_profile_fields(student.get("grading_details"))

    return {
        "member_name": student_name or student_email,
        "roll_number": str(matched_ingestion.get("roll_number") or fallback_details["roll_number"]).strip(),
        "section": str(matched_ingestion.get("section") or fallback_details["section"]).strip(),
        "email_id": student_email or str(matched_ingestion.get("email_id") or "").strip(),
        "contact_number": str(matched_ingestion.get("contact_number") or fallback_details["contact_number"]).strip(),
    }


def _sanitize_excel_cell(value: Any) -> str:
    """Sanitize cell values to avoid openpyxl IllegalCharacterError."""
    text = str(value or "")
    if not text:
        return ""

    cleaned = _ILLEGAL_EXCEL_CHARS_RE.sub("", text)
    # Excel maximum cell text length is 32767.
    if len(cleaned) > 32767:
        cleaned = cleaned[:32767]
    return cleaned


@router.post(
    "",
    response_model=BatchResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RoleChecker(["admin"]))]
)
async def create_batch(
    batch_data: BatchCreateRequest,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Create a new batch (Admin only)
    
    **Required fields:**
    - name: Batch name (e.g., "4th Sem 2024")
    - semester: Semester (e.g., "4th Sem", "6th Sem")
    - year: Year (e.g., 2024)
    - start_date: Batch start date
    - end_date: Batch end date
    
    **Permissions:** Admin only
    """
    try:
        supabase = get_supabase_admin_client()
        
        # Check if batch with same name already exists
        # Note: Multiple batches can have same semester/year (e.g., "3rd Year - 6th Sem 2026" and "3rd Year Honors - 6th Sem 2026")
        # So we check for duplicate names instead
        existing = supabase.table("batches")\
            .select("id")\
            .eq("name", batch_data.name)\
            .execute()
        
        if existing.data and len(existing.data) > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Batch with name '{batch_data.name}' already exists"
            )
        
        # Create batch
        batch = {
            "name": batch_data.name,
            "program": batch_data.program,
            "semester": batch_data.semester,
            "year": batch_data.year,
            "start_date": batch_data.start_date.isoformat(),
            "end_date": batch_data.end_date.isoformat(),
            "status": "active",
            "mentor_rounds": [
                {
                    "id": round_cfg.id,
                    "name": round_cfg.name,
                    "marks_out_of": round_cfg.marks_out_of,
                    "created_at": round_cfg.created_at.isoformat() if round_cfg.created_at else datetime.utcnow().isoformat(),
                }
                for round_cfg in batch_data.mentor_rounds
            ],
        }
        
        result = supabase.table("batches").insert(batch).execute()
        
        if not result.data or len(result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create batch"
            )
        
        created_batch = result.data[0]
        
        return BatchResponse(
            id=UUID(created_batch["id"]),
            name=created_batch["name"],
            program=created_batch.get("program"),
            semester=created_batch["semester"],
            year=created_batch["year"],
            start_date=datetime.fromisoformat(created_batch["start_date"].replace("Z", "+00:00")),
            end_date=datetime.fromisoformat(created_batch["end_date"].replace("Z", "+00:00")),
            status=created_batch["status"],
            team_count=created_batch.get("team_count", 0),
            student_count=created_batch.get("student_count", 0),
            mentor_max_marks=created_batch.get("mentor_max_marks", 100),
            mentor_rounds=_normalize_mentor_rounds(created_batch.get("mentor_rounds")),
            created_at=datetime.fromisoformat(created_batch["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(created_batch["updated_at"].replace("Z", "+00:00"))
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create batch: {str(e)}"
        )


@router.get("", response_model=BatchListResponse)
async def list_batches(
    status_filter: Optional[str] = Query(None, description="Filter by status: active, archived, upcoming"),
    year: Optional[int] = Query(None, description="Filter by year"),
    current_user: Optional[AuthUser] = Depends(get_current_user)
):
    """
    List all batches
    
    **Query parameters:**
    - status: Filter by status (active, archived, upcoming)
    - year: Filter by year
    
    **Permissions:** Authenticated users (mentors and admins)
    """
    try:
        supabase = get_supabase_admin_client()
        
        # Build query
        query = supabase.table("batches").select("*")
        
        if status_filter:
            query = query.eq("status", status_filter)
        
        if year:
            query = query.eq("year", year)
        
        # Order by year desc, then semester
        query = query.order("year", desc=True).order("semester", desc=False)
        
        result = query.execute()
        
        batches = []
        for batch in result.data:
            batches.append(BatchResponse(
                id=UUID(batch["id"]),
                name=batch["name"],
                program=batch.get("program"),
                semester=batch["semester"],
                year=batch["year"],
                start_date=datetime.fromisoformat(batch["start_date"].replace("Z", "+00:00")),
                end_date=datetime.fromisoformat(batch["end_date"].replace("Z", "+00:00")),
                status=batch["status"],
                team_count=batch.get("team_count", 0),
                student_count=batch.get("student_count", 0),
                mentor_max_marks=batch.get("mentor_max_marks", 100),
                mentor_rounds=_normalize_mentor_rounds(batch.get("mentor_rounds")),
                created_at=datetime.fromisoformat(batch["created_at"].replace("Z", "+00:00")),
                updated_at=datetime.fromisoformat(batch["updated_at"].replace("Z", "+00:00"))
            ))
        
        return BatchListResponse(
            batches=batches,
            total=len(batches)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch batches: {str(e)}"
        )


@router.get("/paused/list")
async def list_paused_batches(
    current_user: Optional[AuthUser] = Depends(get_current_user)
):
    """
    Get all batches with paused analysis runs (optimized single query)
    
    Returns only batches that have paused runs with their latest run info.
    This is more efficient than fetching all batches and checking each one.
    
    **Permissions:** Authenticated users
    """
    try:
        supabase = get_supabase_admin_client()
        
        # Get all paused runs with batch info in a single query using join
        runs_result = supabase.table("batch_analysis_runs")\
            .select("batch_id, run_number, status, metadata, batches(id, name, semester, year)")\
            .eq("status", "paused")\
            .order("started_at", desc=True)\
            .execute()
        
        # Group by batch_id and get the latest paused run for each batch
        paused_batches_map = {}
        for run in runs_result.data or []:
            batch_id = run.get("batch_id")
            if batch_id and batch_id not in paused_batches_map:
                batch_info = run.get("batches")
                if batch_info:
                    paused_batches_map[batch_id] = {
                        "batchId": batch_id,
                        "batchName": f"{batch_info.get('semester', '')} {batch_info.get('year', '')}".strip(),
                        "runNumber": run.get("run_number"),
                        "pausedAt": run.get("metadata", {}).get("paused_at") if run.get("metadata") else None
                    }
        
        return {
            "pausedBatches": list(paused_batches_map.values()),
            "total": len(paused_batches_map)
        }
        
    except Exception as e:
        print(f"Error fetching paused batches: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch paused batches: {str(e)}"
        )


@router.get("/{batch_id}", response_model=BatchStatsResponse)
async def get_batch(
    batch_id: UUID,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Get batch by ID with statistics
    
    **Returns:**
    - Basic batch info
    - Team and student counts
    - Average score
    - Project completion stats
    - At-risk team count
    
    **Permissions:** Authenticated users
    """
    try:
        supabase = get_supabase_admin_client()
        
        # Get batch
        batch_result = supabase.table("batches")\
            .select("*")\
            .eq("id", str(batch_id))\
            .execute()
        
        if not batch_result.data or len(batch_result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Batch not found"
            )
        
        batch = batch_result.data[0]
        
        # Get teams in this batch — single query with all needed columns
        teams_result = supabase.table("teams")\
            .select("id, health_status, status, total_score")\
            .eq("batch_id", str(batch_id))\
            .execute()
        
        teams = teams_result.data or []
        
        # Calculate statistics
        at_risk_teams = sum(1 for t in teams if t.get("health_status") in ["at_risk", "critical"])
        
        completed_projects = sum(1 for t in teams if t.get("status") == "completed")
        pending_projects = sum(1 for t in teams if t.get("status") in ["pending", "analyzing"])
        
        # Calculate average score for completed teams
        scores = [t["total_score"] for t in teams if t.get("total_score") is not None]
        avg_score = sum(scores) / len(scores) if scores else None
        
        return BatchStatsResponse(
            id=UUID(batch["id"]),
            name=batch["name"],
            program=batch.get("program"),
            semester=batch["semester"],
            year=batch["year"],
            start_date=datetime.fromisoformat(batch["start_date"].replace("Z", "+00:00")),
            end_date=datetime.fromisoformat(batch["end_date"].replace("Z", "+00:00")),
            status=batch["status"],
            team_count=batch.get("team_count", 0),
            student_count=batch.get("student_count", 0),
            mentor_max_marks=batch.get("mentor_max_marks", 100),
            mentor_rounds=_normalize_mentor_rounds(batch.get("mentor_rounds")),
            avg_score=avg_score,
            completed_projects=completed_projects,
            pending_projects=pending_projects,
            at_risk_teams=at_risk_teams,
            created_at=datetime.fromisoformat(batch["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(batch["updated_at"].replace("Z", "+00:00"))
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch batch: {str(e)}"
        )


@router.put(
    "/{batch_id}",
    response_model=BatchResponse,
    dependencies=[Depends(RoleChecker(["admin"]))]
)
async def update_batch(
    batch_id: UUID,
    batch_data: BatchUpdateRequest,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Update batch (Admin only)
    
    **Updatable fields:**
    - name
    - semester
    - year
    - start_date
    - end_date
    - status
    
    **Permissions:** Admin only
    """
    try:
        supabase = get_supabase_admin_client()
        
        # Check if batch exists
        existing = supabase.table("batches")\
            .select("id")\
            .eq("id", str(batch_id))\
            .execute()
        
        if not existing.data or len(existing.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Batch not found"
            )
        
        # Prepare update data
        update_data = {}
        if batch_data.name is not None:
            update_data["name"] = batch_data.name
        if batch_data.program is not None:
            update_data["program"] = batch_data.program
        if batch_data.semester is not None:
            update_data["semester"] = batch_data.semester
        if batch_data.year is not None:
            update_data["year"] = batch_data.year
        if batch_data.start_date is not None:
            update_data["start_date"] = batch_data.start_date.isoformat()
        if batch_data.end_date is not None:
            update_data["end_date"] = batch_data.end_date.isoformat()
        if batch_data.status is not None:
            update_data["status"] = batch_data.status
        if batch_data.mentor_max_marks is not None:
            update_data["mentor_max_marks"] = batch_data.mentor_max_marks
        if batch_data.mentor_rounds is not None:
            update_data["mentor_rounds"] = [
                {
                    "id": round_cfg.id,
                    "name": round_cfg.name,
                    "marks_out_of": round_cfg.marks_out_of,
                    "created_at": round_cfg.created_at.isoformat() if round_cfg.created_at else datetime.utcnow().isoformat(),
                }
                for round_cfg in batch_data.mentor_rounds
            ]
        
        if not update_data:
            # No updates provided, return current batch
            result = supabase.table("batches")\
                .select("*")\
                .eq("id", str(batch_id))\
                .execute()
            updated_batch = result.data[0]
        else:
            # Update batch
            result = supabase.table("batches")\
                .update(update_data)\
                .eq("id", str(batch_id))\
                .execute()
            
            if not result.data or len(result.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update batch"
                )
            
            updated_batch = result.data[0]
        
        return BatchResponse(
            id=UUID(updated_batch["id"]),
            name=updated_batch["name"],
            program=updated_batch.get("program"),
            semester=updated_batch["semester"],
            year=updated_batch["year"],
            start_date=datetime.fromisoformat(updated_batch["start_date"].replace("Z", "+00:00")),
            end_date=datetime.fromisoformat(updated_batch["end_date"].replace("Z", "+00:00")),
            status=updated_batch["status"],
            team_count=updated_batch.get("team_count", 0),
            student_count=updated_batch.get("student_count", 0),
            mentor_max_marks=updated_batch.get("mentor_max_marks", 100),
            mentor_rounds=_normalize_mentor_rounds(updated_batch.get("mentor_rounds")),
            created_at=datetime.fromisoformat(updated_batch["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(updated_batch["updated_at"].replace("Z", "+00:00"))
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update batch: {str(e)}"
        )


@router.get("/{batch_id}/mentor-rounds", response_model=MentorRoundListResponse)
async def list_mentor_rounds(
    batch_id: UUID,
    current_user: AuthUser = Depends(get_current_user)
):
    """List configured mentor grading rounds for a batch."""
    try:
        supabase = get_supabase_admin_client()
        batch_result = supabase.table("batches").select("id, mentor_rounds").eq("id", str(batch_id)).limit(1).execute()

        if not batch_result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

        rounds = _normalize_mentor_rounds(batch_result.data[0].get("mentor_rounds"))
        return MentorRoundListResponse(batch_id=batch_id, rounds=rounds)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch mentor rounds: {str(e)}"
        )


@router.post(
    "/{batch_id}/mentor-rounds",
    response_model=MentorRoundListResponse,
    dependencies=[Depends(RoleChecker(["admin"]))]
)
async def create_mentor_round(
    batch_id: UUID,
    round_data: MentorRoundCreateRequest,
    request: Request,
    current_user: AuthUser = Depends(get_current_user)
):
    """Create a mentor grading round for a batch (Admin only)."""
    try:
        supabase = get_supabase_admin_client()
        batch_result = (
            supabase
            .table("batches")
            .select("id, name, mentor_rounds")
            .eq("id", str(batch_id))
            .limit(1)
            .execute()
        )

        if not batch_result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

        batch_data = batch_result.data[0]
        batch_name = str(batch_data.get("name") or "").strip() or "Selected Batch"
        rounds = _normalize_mentor_rounds(batch_data.get("mentor_rounds"))
        existing_names = {str(r.get("name", "")).strip().lower() for r in rounds}
        new_name = round_data.name.strip()

        if new_name.lower() in existing_names:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Mentor round '{new_name}' already exists in this batch"
            )

        rounds.append({
            "id": str(uuid4()),
            "name": new_name,
            "marks_out_of": round_data.marks_out_of,
            "created_at": datetime.utcnow().isoformat(),
        })

        supabase.table("batches").update({"mentor_rounds": rounds}).eq("id", str(batch_id)).execute()

        requester_name = str(current_user.full_name or current_user.email or "ProjectFlow Admin").strip()
        request_origin = str(request.headers.get("origin") or "").strip().rstrip("/")
        frontend_url_override = request_origin
        try:
            _notify_assigned_mentors_for_round(
                supabase=supabase,
                batch_id=batch_id,
                batch_name=batch_name,
                round_name=new_name,
                requested_by=requester_name,
                frontend_url_override=frontend_url_override,
            )
        except Exception as e:
            # Do not block round creation if notifications fail.
            print(f"[Batches] Mentor round notification flow failed: {e}")

        return MentorRoundListResponse(batch_id=batch_id, rounds=rounds)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create mentor round: {str(e)}"
        )


@router.delete(
    "/{batch_id}/mentor-rounds/{round_id}",
    response_model=MentorRoundListResponse,
    dependencies=[Depends(RoleChecker(["admin"]))]
)
async def delete_mentor_round(
    batch_id: UUID,
    round_id: str,
    current_user: AuthUser = Depends(get_current_user)
):
    """Delete a mentor grading round from a batch (Admin only)."""
    try:
        supabase = get_supabase_admin_client()
        batch_result = supabase.table("batches").select("id, mentor_rounds").eq("id", str(batch_id)).limit(1).execute()

        if not batch_result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

        rounds = _normalize_mentor_rounds(batch_result.data[0].get("mentor_rounds"))
        filtered_rounds = [r for r in rounds if str(r.get("id")) != str(round_id)]

        if len(filtered_rounds) == len(rounds):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mentor round not found")

        supabase.table("batches").update({"mentor_rounds": filtered_rounds}).eq("id", str(batch_id)).execute()
        return MentorRoundListResponse(batch_id=batch_id, rounds=filtered_rounds)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete mentor round: {str(e)}"
        )


@router.put(
    "/{batch_id}/mentor-rounds/{round_id}",
    response_model=MentorRoundListResponse,
    dependencies=[Depends(RoleChecker(["admin"]))]
)
async def update_mentor_round(
    batch_id: UUID,
    round_id: str,
    round_data: MentorRoundUpdateRequest,
    current_user: AuthUser = Depends(get_current_user)
):
    """Update a mentor grading round in a batch (Admin only)."""
    try:
        supabase = get_supabase_admin_client()
        batch_result = supabase.table("batches").select("id, mentor_rounds").eq("id", str(batch_id)).limit(1).execute()

        if not batch_result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

        rounds = _normalize_mentor_rounds(batch_result.data[0].get("mentor_rounds"))
        new_name = round_data.name.strip()

        existing_names = {
            str(r.get("name", "")).strip().lower()
            for r in rounds
            if str(r.get("id")) != str(round_id)
        }
        if new_name.lower() in existing_names:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Mentor round '{new_name}' already exists in this batch"
            )

        updated = False
        for idx, round_cfg in enumerate(rounds):
            if str(round_cfg.get("id")) != str(round_id):
                continue

            rounds[idx] = {
                "id": str(round_cfg.get("id")),
                "name": new_name,
                "marks_out_of": round_data.marks_out_of,
                "created_at": round_cfg.get("created_at") or datetime.utcnow().isoformat(),
            }
            updated = True
            break

        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mentor round not found")

        supabase.table("batches").update({"mentor_rounds": rounds}).eq("id", str(batch_id)).execute()
        return MentorRoundListResponse(batch_id=batch_id, rounds=rounds)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update mentor round: {str(e)}"
        )


@router.get(
    "/{batch_id}/grades-csv",
    dependencies=[Depends(RoleChecker(["admin"]))]
)
async def download_batch_grades_csv(
    batch_id: UUID,
    round_id: Optional[str] = Query(None, description="Optional mentor round id for round-specific export"),
    export_format: str = Query("csv", pattern="^(csv|xlsx)$", description="Export format: csv or xlsx"),
    current_user: AuthUser = Depends(get_current_user)
):
    """Download mentor grades export for one batch (Admin only)."""
    try:
        supabase = get_supabase_admin_client()

        batch_result = supabase.table("batches").select("id, name, mentor_rounds").eq("id", str(batch_id)).limit(1).execute()
        if not batch_result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

        batch_data = batch_result.data[0]
        rounds = _normalize_mentor_rounds(batch_data.get("mentor_rounds"))
        round_name_map = {str(round_cfg.get("id")): str(round_cfg.get("name")) for round_cfg in rounds}

        teams_result = supabase.table("teams").select("id, team_name, mentor_id, repo_url, metadata").eq("batch_id", str(batch_id)).order("team_name").execute()
        teams = teams_result.data or []

        team_map: Dict[str, Dict[str, Any]] = {str(team.get("id")): team for team in teams if team.get("id")}
        team_ids = list(team_map.keys())
        mentor_name_map: Dict[str, str] = {}

        mentor_ids = {str(team.get("mentor_id")) for team in teams if team.get("mentor_id")}
        if mentor_ids:
            mentors_result = supabase.table("users").select("id, full_name, email").in_("id", list(mentor_ids)).execute()
            for mentor in mentors_result.data or []:
                mentor_id = str(mentor.get("id") or "")
                if not mentor_id:
                    continue
                mentor_name_map[mentor_id] = str(mentor.get("full_name") or mentor.get("email") or "").strip()

        students: List[Dict[str, Any]] = []
        graded_round_ids = set()

        if team_ids:
            students_result = supabase.table("students").select("team_id, name, email, grading_details").in_("team_id", team_ids).order("name").execute()
            students = students_result.data or []

            for student in students:
                grading_details = student.get("grading_details")
                if not isinstance(grading_details, dict):
                    continue

                for raw_round_id, round_data in grading_details.items():
                    normalized_round_id = str(raw_round_id)
                    if _has_round_data(round_data):
                        graded_round_ids.add(normalized_round_id)

        selected_round_id: Optional[str] = str(round_id).strip() if round_id else None
        if selected_round_id:
            if selected_round_id not in graded_round_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No graded data found for round '{selected_round_id}' in this batch"
                )
        elif len(graded_round_ids) == 1:
            selected_round_id = next(iter(graded_round_ids))
        elif len(graded_round_ids) > 1:
            # Prefer the latest configured mentor round that has graded data.
            configured_graded_round_ids = [
                str(round_cfg.get("id"))
                for round_cfg in rounds
                if str(round_cfg.get("id")) in graded_round_ids
            ]
            if configured_graded_round_ids:
                selected_round_id = configured_graded_round_ids[-1]
            else:
                # Fallback for legacy/unmapped round keys in grading_details.
                selected_round_id = sorted(graded_round_ids)[-1]

        fieldnames = [
            "Team No",
            "Member Name",
            "Roll Number",
            "Section",
            "Email ID",
            "Project Statement",
            "Mentor",
            "Github Repository",
            "Marks",
        ]
        rows_to_export: List[Dict[str, str]] = []
        merged_team_ranges: List[Dict[str, int]] = []

        students_by_team: Dict[str, List[Dict[str, Any]]] = {}
        for student in students:
            team_id = str(student.get("team_id") or "").strip()
            if not team_id:
                continue
            students_by_team.setdefault(team_id, []).append(student)

        for team in teams:
            team_id = str(team.get("id") or "").strip()
            if not team_id:
                continue

            team_students = students_by_team.get(team_id, [])
            if not team_students:
                continue

            team_name = str(team.get("team_name") or "").strip()
            mentor_id = str(team.get("mentor_id") or "").strip()
            team_metadata = team.get("metadata") if isinstance(team.get("metadata"), dict) else {}
            ingestion_data = team_metadata.get("ingestion") if isinstance(team_metadata.get("ingestion"), dict) else {}
            ingestion_students = ingestion_data.get("students") if isinstance(ingestion_data.get("students"), list) else []

            mentor_name = mentor_name_map.get(mentor_id, "")
            if not mentor_name:
                mentor_name = str(ingestion_data.get("mentor") or "").strip()

            project_statement = str(ingestion_data.get("project_statement") or "").strip()
            if not project_statement:
                project_statement = team_name

            github_repository = str(team.get("repo_url") or "").strip()
            if not github_repository:
                github_repository = str(ingestion_data.get("github_repository") or "").strip()

            team_no = str(ingestion_data.get("team_no") or "").strip() or _extract_team_no(team_name)

            team_start_row = len(rows_to_export) + 2

            for student_index, student in enumerate(team_students):
                student_fields = _resolve_student_export_fields(student, ingestion_students)
                round_row = _extract_single_round_row(student.get("grading_details"), selected_round_id, round_name_map)

                rows_to_export.append({
                    "Team No": team_no if student_index == 0 else "",
                    "Member Name": student_fields["member_name"],
                    "Roll Number": student_fields["roll_number"],
                    "Section": student_fields["section"],
                    "Email ID": student_fields["email_id"],
                    "Project Statement": project_statement if student_index == 0 else "",
                    "Mentor": mentor_name,
                    "Github Repository": github_repository,
                    "Marks": round_row.get("marks") or "",
                })

            merged_team_ranges.append({
                "start_row": team_start_row,
                "end_row": len(rows_to_export) + 1,
            })

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        batch_name = str(batch_data.get("name") or "batch").strip().replace(" ", "_")
        round_suffix = "all_rounds"
        if selected_round_id:
            round_suffix = re.sub(r"[^a-zA-Z0-9_-]+", "_", round_name_map.get(selected_round_id, selected_round_id)).strip("_") or "round"

        if export_format == "xlsx":
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font
            from openpyxl.utils import get_column_letter

            workbook = Workbook()
            worksheet = workbook.active
            worksheet.title = "Master Sheet"

            worksheet.append(fieldnames)
            for row in rows_to_export:
                worksheet.append([_sanitize_excel_cell(row.get(col, "")) for col in fieldnames])

            for team_range in merged_team_ranges:
                if team_range["end_row"] <= team_range["start_row"]:
                    continue
                worksheet.merge_cells(start_row=team_range["start_row"], start_column=1, end_row=team_range["end_row"], end_column=1)
                worksheet.merge_cells(start_row=team_range["start_row"], start_column=6, end_row=team_range["end_row"], end_column=6)
                worksheet.merge_cells(start_row=team_range["start_row"], start_column=7, end_row=team_range["end_row"], end_column=7)
                worksheet.merge_cells(start_row=team_range["start_row"], start_column=8, end_row=team_range["end_row"], end_column=8)

            header_font = Font(bold=True)
            for col_idx in range(1, len(fieldnames) + 1):
                cell = worksheet.cell(row=1, column=col_idx)
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

            max_width_cap = 80
            min_width = 12
            for col_idx, col_name in enumerate(fieldnames, start=1):
                max_len = len(col_name)
                for row in rows_to_export:
                    max_len = max(max_len, len(str(row.get(col_name, ""))))
                adjusted_width = min(max_width_cap, max(min_width, max_len + 2))
                worksheet.column_dimensions[get_column_letter(col_idx)].width = adjusted_width

            worksheet.column_dimensions[get_column_letter(6)].width = min(max_width_cap, max(24, worksheet.column_dimensions[get_column_letter(6)].width or 24))
            worksheet.column_dimensions[get_column_letter(9)].width = min(max_width_cap, max(12, worksheet.column_dimensions[get_column_letter(9)].width or 12))

            for row_idx in range(2, len(rows_to_export) + 2):
                for col_idx in range(1, len(fieldnames) + 1):
                    worksheet.cell(row=row_idx, column=col_idx).alignment = Alignment(vertical="top", wrap_text=True)

            for team_range in merged_team_ranges:
                for merged_col in (1, 6, 7, 8):
                    worksheet.cell(row=team_range["start_row"], column=merged_col).alignment = Alignment(vertical="top", wrap_text=True)

            worksheet.freeze_panes = "A2"

            excel_output = io.BytesIO()
            workbook.save(excel_output)
            excel_output.seek(0)

            filename = f"{batch_name}_mentor_grades_{round_suffix}_{timestamp}.xlsx"
            return StreamingResponse(
                iter([excel_output.getvalue()]),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )

        output = io.StringIO()
        # Helps Excel interpret delimiter correctly and prevents merged columns.
        output.write("sep=,\n")
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows_to_export:
            writer.writerow(row)

        output.seek(0)
        filename = f"{batch_name}_mentor_grades_{round_suffix}_{timestamp}.csv"

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate grades CSV: {str(e)}"
        )


@router.get(
    "/{batch_id}/individual-marks-leaderboard",
    dependencies=[Depends(RoleChecker(["admin"]))]
)
async def get_individual_marks_leaderboard(
    batch_id: UUID,
    round_id: Optional[str] = Query(None, description="Optional mentor round id for round-specific leaderboard"),
    current_user: AuthUser = Depends(get_current_user)
):
    """Get individual student marks leaderboard for one batch (Admin only)."""
    try:
        supabase = get_supabase_admin_client()

        batch_result = supabase.table("batches").select("id, name, mentor_rounds").eq("id", str(batch_id)).limit(1).execute()
        if not batch_result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

        batch_data = batch_result.data[0]
        rounds = _normalize_mentor_rounds(batch_data.get("mentor_rounds"))
        round_name_map = {str(round_cfg.get("id")): str(round_cfg.get("name")) for round_cfg in rounds}

        include_project_id = True
        try:
            teams_result = (
                supabase
                .table("teams")
                .select("id, team_name, mentor_id, project_id")
                .eq("batch_id", str(batch_id))
                .order("team_name")
                .execute()
            )
            teams = teams_result.data or []
        except Exception as teams_error:
            if not _is_missing_project_id_column_error(teams_error):
                raise

            include_project_id = False
            teams_result = (
                supabase
                .table("teams")
                .select("id, team_name, mentor_id")
                .eq("batch_id", str(batch_id))
                .order("team_name")
                .execute()
            )
            teams = teams_result.data or []

        # Fetch project names for teams
        project_name_map: Dict[str, str] = {}
        project_ids = {str(team.get("project_id")) for team in teams if team.get("project_id")}
        if include_project_id and project_ids:
            projects_result = supabase.table("projects").select("id, name").in_("id", list(project_ids)).execute()
            for project in projects_result.data or []:
                project_id = str(project.get("id") or "")
                if project_id:
                    project_name_map[project_id] = str(project.get("name") or "").strip()

        team_map: Dict[str, Dict[str, Any]] = {str(team.get("id")): team for team in teams if team.get("id")}
        team_ids = list(team_map.keys())
        mentor_name_map: Dict[str, str] = {}

        mentor_ids = {str(team.get("mentor_id")) for team in teams if team.get("mentor_id")}
        if mentor_ids:
            mentors_result = supabase.table("users").select("id, full_name, email").in_("id", list(mentor_ids)).execute()
            for mentor in mentors_result.data or []:
                mentor_id = str(mentor.get("id") or "")
                if not mentor_id:
                    continue
                mentor_name_map[mentor_id] = str(mentor.get("full_name") or mentor.get("email") or "").strip()

        students: List[Dict[str, Any]] = []
        graded_round_ids = set()

        if team_ids:
            students_result = supabase.table("students").select("team_id, name, email, grading_details").in_("team_id", team_ids).order("name").execute()
            students = students_result.data or []

            for student in students:
                grading_details = student.get("grading_details")
                if not isinstance(grading_details, dict):
                    continue

                for raw_round_id, round_data in grading_details.items():
                    normalized_round_id = str(raw_round_id)
                    if _has_round_data(round_data):
                        graded_round_ids.add(normalized_round_id)

        selected_round_id: Optional[str] = str(round_id).strip() if round_id else None
        if selected_round_id:
            if selected_round_id not in graded_round_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No graded data found for round '{selected_round_id}' in this batch"
                )
        elif len(graded_round_ids) == 1:
            selected_round_id = next(iter(graded_round_ids))
        elif len(graded_round_ids) > 1:
            available_rounds = [
                {
                    "id": str(round_cfg.get("id")),
                    "name": str(round_cfg.get("name")),
                }
                for round_cfg in rounds
                if str(round_cfg.get("id")) in graded_round_ids
            ]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Multiple graded rounds found. Please pass round_id to view one leaderboard.",
                    "available_rounds": available_rounds,
                }
            )

        students_by_team: Dict[str, List[Dict[str, Any]]] = {}
        for student in students:
            team_id = str(student.get("team_id") or "").strip()
            if not team_id:
                continue
            students_by_team.setdefault(team_id, []).append(student)

        leaderboard_rows: List[Dict[str, Any]] = []
        round_label = round_name_map.get(selected_round_id or "", selected_round_id or "")

        for team in teams:
            team_id = str(team.get("id") or "").strip()
            if not team_id:
                continue

            team_name = str(team.get("team_name") or "")
            mentor_id = str(team.get("mentor_id") or "").strip()
            mentor_name = mentor_name_map.get(mentor_id, "")
            project_id = str(team.get("project_id") or "").strip() if include_project_id else ""
            project_name = project_name_map.get(project_id, "")
            team_students = students_by_team.get(team_id, [])

            if not team_students:
                leaderboard_rows.append({
                    "teamId": team_id,
                    "teamNo": _extract_team_no(team_name),
                    "teamName": team_name,
                    "projectName": project_name,
                    "mentorName": mentor_name,
                    "teamMemberName": "",
                    "round": round_label,
                    "marks": "",
                    "feedback": "",
                    "marksValue": None,
                })
                continue

            for student in team_students:
                round_row = _extract_single_round_row(student.get("grading_details"), selected_round_id, round_name_map)
                marks_value = _parse_mark_as_float(round_row.get("marks"))

                leaderboard_rows.append({
                    "teamId": team_id,
                    "teamNo": _extract_team_no(team_name),
                    "teamName": team_name,
                    "projectName": project_name,
                    "mentorId": str(team.get("mentor_id") or "").strip(),
                    "mentorName": mentor_name,
                    "teamMemberName": str(student.get("name") or "").strip() or str(student.get("email") or "").strip(),
                    "round": round_row.get("round") or round_label,
                    "marks": round_row.get("marks") or "",
                    "feedback": round_row.get("feedback") or "",
                    "marksValue": marks_value,
                })

        leaderboard_rows.sort(
            key=lambda item: (
                item.get("marksValue") is None,
                -(float(item.get("marksValue") or 0)),
                str(item.get("teamMemberName") or "").strip() == "",
                str(item.get("teamMemberName") or "").lower(),
            )
        )

        ranked_rows: List[Dict[str, Any]] = []
        for index, item in enumerate(leaderboard_rows, start=1):
            ranked_rows.append({
                "rank": index,
                "teamId": item.get("teamId") or "",
                "teamNo": item.get("teamNo") or "",
                "teamName": item.get("teamName") or "",
                "projectName": item.get("projectName") or "",
                "mentorId": item.get("mentorId") or "",
                "mentorName": item.get("mentorName") or "",
                "teamMemberName": item.get("teamMemberName") or "",
                "round": item.get("round") or "",
                "marks": item.get("marks") or "",
                "feedback": item.get("feedback") or "",
            })

        return {
            "batch_id": str(batch_id),
            "batch_name": str(batch_data.get("name") or ""),
            "round_id": selected_round_id,
            "round_name": round_label,
            "leaderboard": ranked_rows,
            "total": len(ranked_rows),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch individual marks leaderboard: {str(e)}"
        )


@router.post(
    "/{batch_id}/mentor-marks-reminder/bulk",
    dependencies=[Depends(RoleChecker(["admin"]))]
)
async def send_bulk_mentor_marks_reminder(
    batch_id: UUID,
    payload: MentorMarksReminderBulkRequest,
    round_id: Optional[str] = Query(None, description="Optional round id for round-specific reminder text"),
    current_user: AuthUser = Depends(get_current_user),
):
    """Send one reminder email to the assigned mentor for multiple teams in the same batch."""
    try:
        team_ids = [str(team_id).strip() for team_id in payload.team_ids if str(team_id).strip()]
        if not team_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one team must be provided")

        supabase = get_supabase_admin_client()

        batch_result = (
            supabase
            .table("batches")
            .select("id, name, mentor_rounds")
            .eq("id", str(batch_id))
            .limit(1)
            .execute()
        )
        if not batch_result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

        batch_data = batch_result.data[0]
        batch_name = str(batch_data.get("name") or "").strip() or "Selected Batch"
        rounds = _normalize_mentor_rounds(batch_data.get("mentor_rounds"))
        round_label = _resolve_round_label(batch_rounds=rounds, round_id=round_id)

        team_result = (
            supabase
            .table("teams")
            .select("id, team_name, mentor_id")
            .eq("batch_id", str(batch_id))
            .in_("id", team_ids)
            .execute()
        )
        team_rows = team_result.data or []
        if len(team_rows) != len(team_ids):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more teams were not found in this batch")

        team_by_id = {str(team.get("id") or "").strip(): team for team in team_rows}
        ordered_team_names: List[str] = []
        mentor_ids = set()
        for team_id_value in team_ids:
            team_data = team_by_id.get(team_id_value)
            if not team_data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more teams were not found in this batch")

            mentor_id = str(team_data.get("mentor_id") or "").strip()
            if not mentor_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No mentor is assigned to one or more selected teams")

            mentor_ids.add(mentor_id)
            ordered_team_names.append(str(team_data.get("team_name") or "").strip() or "Unknown Team")

        if len(mentor_ids) != 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected teams must belong to the same mentor")

        mentor_id = next(iter(mentor_ids))
        mentor_result = (
            supabase
            .table("users")
            .select("id, email, full_name")
            .eq("id", mentor_id)
            .limit(1)
            .execute()
        )
        if not mentor_result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned mentor not found")

        mentor_data = mentor_result.data[0]
        mentor_email = str(mentor_data.get("email") or "").strip()
        mentor_name = str(mentor_data.get("full_name") or "").strip() or "Mentor"
        if not mentor_email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assigned mentor does not have an email address")

        sender_name = str(current_user.full_name or current_user.email or "ProjectFlow Admin").strip()

        subject = EmailTemplates.mentor_marks_bulk_reminder_subject(
            batch_name=batch_name,
            round_name=round_label,
            team_count=len(ordered_team_names),
        )
        email_parts = EmailTemplates.mentor_marks_bulk_reminder_body(
            mentor_name=mentor_name,
            team_names=ordered_team_names,
            batch_name=batch_name,
            round_name=round_label,
            requested_by=sender_name,
        )

        send_alert_email(
            subject=subject,
            body_text=email_parts["text"],
            html_body=email_parts["html"],
            to_email=mentor_email,
            use_mentor_sender=True,
        )

        return {
            "message": f"Reminder email sent to mentor for {len(ordered_team_names)} teams",
            "team_ids": team_ids,
            "team_names": ordered_team_names,
            "mentor_email": mentor_email,
            "round": round_label,
        }
    except HTTPException:
        raise
    except EmailConfigError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Email service is unavailable: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send mentor reminder: {str(e)}",
        )


@router.post(
    "/{batch_id}/mentor-marks-reminder/{team_id}",
    dependencies=[Depends(RoleChecker(["admin"]))]
)
async def send_mentor_marks_reminder(
    batch_id: UUID,
    team_id: UUID,
    round_id: Optional[str] = Query(None, description="Optional round id for round-specific reminder text"),
    current_user: AuthUser = Depends(get_current_user),
):
    """Send a reminder email to the assigned mentor when a team has missing marks."""
    try:
        supabase = get_supabase_admin_client()

        batch_result = (
            supabase
            .table("batches")
            .select("id, name, mentor_rounds")
            .eq("id", str(batch_id))
            .limit(1)
            .execute()
        )
        if not batch_result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

        batch_data = batch_result.data[0]
        batch_name = str(batch_data.get("name") or "").strip() or "Selected Batch"
        rounds = _normalize_mentor_rounds(batch_data.get("mentor_rounds"))
        round_label = _resolve_round_label(batch_rounds=rounds, round_id=round_id)

        team_result = (
            supabase
            .table("teams")
            .select("id, team_name, mentor_id")
            .eq("id", str(team_id))
            .eq("batch_id", str(batch_id))
            .limit(1)
            .execute()
        )
        if not team_result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found in this batch")

        team_data = team_result.data[0]
        team_name = str(team_data.get("team_name") or "").strip() or "Unknown Team"
        mentor_id = str(team_data.get("mentor_id") or "").strip()
        if not mentor_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No mentor is assigned to this team")

        mentor_result = (
            supabase
            .table("users")
            .select("id, email, full_name")
            .eq("id", mentor_id)
            .limit(1)
            .execute()
        )
        if not mentor_result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned mentor not found")

        mentor_data = mentor_result.data[0]
        mentor_email = str(mentor_data.get("email") or "").strip()
        mentor_name = str(mentor_data.get("full_name") or "").strip() or "Mentor"
        if not mentor_email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assigned mentor does not have an email address")

        sender_name = str(current_user.full_name or current_user.email or "ProjectFlow Admin").strip()

        subject = EmailTemplates.mentor_marks_reminder_subject(
            team_name=team_name,
            round_name=round_label,
        )
        email_parts = EmailTemplates.mentor_marks_reminder_body(
            mentor_name=mentor_name,
            team_name=team_name,
            batch_name=batch_name,
            round_name=round_label,
            requested_by=sender_name,
        )

        send_alert_email(
            subject=subject,
            body_text=email_parts["text"],
            html_body=email_parts["html"],
            to_email=mentor_email,
            use_mentor_sender=True,
        )

        return {
            "message": "Reminder email sent to mentor",
            "team_id": str(team_id),
            "mentor_email": mentor_email,
            "round": round_label,
        }
    except HTTPException:
        raise
    except EmailConfigError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Email service is unavailable: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send mentor reminder: {str(e)}",
        )


@router.get(
    "/{batch_id}/individual-marks-leaderboard-csv",
    dependencies=[Depends(RoleChecker(["admin"]))]
)
async def download_individual_marks_leaderboard_csv(
    batch_id: UUID,
    round_id: Optional[str] = Query(None, description="Optional mentor round id for round-specific leaderboard export"),
    current_user: AuthUser = Depends(get_current_user)
):
    """Download individual marks leaderboard CSV for one batch (Admin only)."""
    try:
        leaderboard_payload = await get_individual_marks_leaderboard(batch_id=batch_id, round_id=round_id, current_user=current_user)

        rows = leaderboard_payload.get("leaderboard") or []
        round_name = str(leaderboard_payload.get("round_name") or "")
        batch_name = str(leaderboard_payload.get("batch_name") or "batch")

        output = io.StringIO()
        # Helps Excel interpret delimiter correctly and prevents merged columns.
        output.write("sep=,\n")
        writer = csv.DictWriter(output, fieldnames=["Sr No.", "Team No.", "Project Name", "Mentor Name", "Team Members", "Individual Scoring", "Feedback"])
        writer.writeheader()

        for row in rows:
            writer.writerow({
                "Sr No.": row.get("rank") or "",
                "Team No.": row.get("teamNo") or "",
                "Project Name": row.get("projectName") or "",
                "Mentor Name": row.get("mentorName") or "",
                "Team Members": row.get("teamMemberName") or "",
                "Individual Scoring": row.get("marks") or "",
                "Feedback": row.get("feedback") or "",
            })

        output.seek(0)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_batch_name = batch_name.strip().replace(" ", "_") or "batch"
        round_suffix = re.sub(r"[^a-zA-Z0-9_-]+", "_", round_name).strip("_") or "round"
        filename = f"{safe_batch_name}_individual_marks_leaderboard_{round_suffix}_{timestamp}.csv"

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate individual marks leaderboard CSV: {str(e)}"
        )


@router.post(
    "/{batch_id}/analyze",
    dependencies=[Depends(RoleChecker(["admin"]))]
)
async def trigger_batch_analysis(
    batch_id: UUID,
    force: bool = Query(False, description="Force re-analysis of all teams, ignoring the 7-day interval"),
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Trigger weekly analysis for all teams in a batch (Admin only)
    
    Creates a new batch_analysis_run and queues analysis jobs for teams using Celery.
    
    By default, only teams that haven't been analyzed within the last 7 days will be
    included. Use force=true to re-analyze all teams regardless of when they were last analyzed.
    
    **Permissions:** Admin only
    """
    try:
        # Import Celery task (may fail if in separate container, but that's OK)
        try:
            from celery_worker import process_batch_sequential
            CELERY_ENABLED = True
        except ImportError:
            # Try importing from celery_app instead (works across containers)
            try:
                from celery_app import celery_app
                process_batch_sequential = celery_app.signature('celery_worker.process_batch_sequential')
                CELERY_ENABLED = True
            except:
                CELERY_ENABLED = False
        
        supabase = get_supabase_admin_client()
        
        # Check if batch exists
        batch_result = supabase.table("batches")\
            .select("id, start_date")\
            .eq("id", str(batch_id))\
            .execute()
        
        if not batch_result.data or len(batch_result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Batch not found"
            )
        
        # Calculate current week number
        batch = batch_result.data[0]
        
        # Get all teams in this batch (projects table has been dropped)
        teams_result = supabase.table("teams")\
            .select("id, team_name, repo_url, status, last_analyzed_at")\
            .eq("batch_id", str(batch_id))\
            .execute()
        
        teams = teams_result.data or []
        total_teams = len(teams)
        
        if total_teams == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No teams found in this batch"
            )
        
        # Get current run number (last run + 1)
        last_run_result = supabase.table("batch_analysis_runs")\
            .select("run_number")\
            .eq("batch_id", str(batch_id))\
            .order("run_number", desc=True)\
            .limit(1)\
            .execute()
        
        run_number = 1
        if last_run_result.data and len(last_run_result.data) > 0:
            run_number = last_run_result.data[0]["run_number"] + 1
        
        # Create batch analysis run
        run_insert = {
            "batch_id": str(batch_id),
            "run_number": run_number,
            "status": "pending",
            "total_teams": total_teams,
            "completed_teams": 0,
            "failed_teams": 0
        }
        
        run_result = supabase.table("batch_analysis_runs")\
            .insert(run_insert)\
            .execute()
        
        if not run_result.data or len(run_result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create batch analysis run"
            )
        
        run_id = run_result.data[0]["id"]
        
        # Build repos list for batch processing
        repos = []
        jobs_created = 0
        jobs_skipped = 0
        skipped_reasons = []
        
        # Import re-analysis check
        from src.api.backend.routers.analysis import should_allow_reanalysis
        
        for team in teams:
            # Projects table has been dropped - all data is now in teams table
            team_id = team["id"]
            repo_url = team.get("repo_url")
            
            # Skip teams with empty or missing repo URLs and mark them as failed
            if not repo_url or repo_url.strip() == "":
                jobs_skipped += 1
                skipped_reasons.append(f"{team['team_name']}: No repository URL")
                
                # Mark team as failed immediately
                try:
                    supabase.table("teams").update({
                        "status": "failed",
                        "last_analyzed_at": datetime.now().isoformat()
                    }).eq("id", team_id).execute()
                    
                    # Create a failed job record for tracking
                    from uuid import uuid4
                    job_insert = {
                        "id": str(uuid4()),  # Generate UUID for job
                        "team_id": team_id,
                        "status": "failed",
                        "progress": 0,
                        "error_message": "Repository URL is missing or empty. Cannot proceed with analysis.",
                        "requested_by": str(current_user.user_id),
                        "started_at": datetime.now().isoformat(),
                        "completed_at": datetime.now().isoformat(),
                        "metadata": {
                            "batch_run_id": run_id,
                            "run_number": run_number,
                            "team_id": team_id,
                            "skip_reason": "empty_repo_url"
                        }
                    }
                    supabase.table("analysis_jobs").insert(job_insert).execute()
                except Exception as e:
                    print(f"Failed to mark team {team['team_name']} as failed: {e}")
                
                continue
            
            # Check if re-analysis should be allowed (auto-scheduled analysis respects interval)
            # Pass team data directly (team is now the project)
            allowed, reason = should_allow_reanalysis(team, force=force)
            if not allowed:
                jobs_skipped += 1
                skipped_reasons.append(f"{team['team_name']}: {reason}")
                continue
            
            # Create analysis job
            job_insert = {
                "team_id": team_id,  # Changed from project_id to team_id
                "status": "queued",
                "requested_by": str(current_user.user_id),
                "started_at": datetime.now().isoformat(),
                "metadata": {
                    "batch_run_id": run_id,
                    "run_number": run_number,
                    "team_id": team_id
                }
            }
            
            try:
                job_result = supabase.table("analysis_jobs").insert(job_insert).execute()
                job_id = job_result.data[0]["id"]
                
                # Update team status (projects table has been dropped)
                # Note: 'queued' is not a valid status for teams table
                # Valid statuses are: pending, analyzing, completed, failed
                supabase.table("teams").update({
                    "status": "analyzing"
                }).eq("id", team_id).execute()
                
                repos.append({
                    "team_id": team_id,
                    "job_id": job_id,
                    "repo_url": repo_url,
                    "team_name": team["team_name"]
                })
                jobs_created += 1
            except Exception as e:
                print(f"Failed to create job for team {team['team_name']}: {e}")
                jobs_skipped += 1
                skipped_reasons.append(f"{team['team_name']}: {str(e)}")
        
        # Queue Celery batch task (or fallback to sequential processing)
        celery_queued = False
        print(f"[DEBUG] CELERY_ENABLED={CELERY_ENABLED}, repos count={len(repos)}")
        
        if CELERY_ENABLED and repos:
            try:
                if callable(process_batch_sequential):
                    # Direct import worked
                    task = process_batch_sequential.delay(str(batch_id), repos)
                else:
                    # Using signature (cross-container)
                    task = process_batch_sequential.apply_async(args=[str(batch_id), repos])
                
                # Store Celery task ID
                supabase.table("batch_analysis_runs").update({
                    "status": "running",
                    "started_at": datetime.now().isoformat(),
                    "metadata": {"celery_task_id": task.id}
                }).eq("id", run_id).execute()
                celery_queued = True
                print(f"✓ Batch analysis queued via Celery (task_id: {task.id})")
            except Exception as celery_error:
                print(f"⚠ Celery queueing failed: {celery_error}")
                print(f"  Error type: {type(celery_error).__name__}")
                import traceback
                traceback.print_exc()
                print("  Marking all created jobs as failed due to Celery unavailability...")
                
                # CRITICAL FIX: Mark all newly created jobs as failed
                # This prevents the "stuck in queued" problem (Team 98 scenario)
                try:
                    for repo in repos:
                        job_id = repo.get('job_id')
                        team_id = repo.get('team_id')
                        
                        if job_id:
                            supabase.table("analysis_jobs").update({
                                "status": "failed",
                                "error_message": f"Celery task submission failed: {str(celery_error)}",
                                "completed_at": datetime.now().isoformat()
                            }).eq("id", job_id).execute()
                        
                        # Reset team status back to previous state
                        if team_id:
                            supabase.table("teams").update({
                                "status": "pending"  # or "active" if previously analyzed
                            }).eq("id", team_id).execute()
                    
                    print(f"  ✓ Marked {len(repos)} jobs as failed")
                    
                except Exception as cleanup_error:
                    print(f"  ❌ Failed to cleanup jobs: {cleanup_error}")
                
                # Mark batch run as failed
                supabase.table("batch_analysis_runs").update({
                    "status": "failed",
                    "started_at": datetime.now().isoformat(),
                    "completed_at": datetime.now().isoformat(),
                    "metadata": {"error": f"Celery unavailable: {str(celery_error)}"}
                }).eq("id", run_id).execute()
                
                # Raise HTTP exception so frontend knows it failed
                raise HTTPException(
                    status_code=503,
                    detail=f"Analysis service unavailable: {str(celery_error)}"
                )
        
        # Fallback: If Celery is not available or no repos to process
        if not celery_queued:
            supabase.table("batch_analysis_runs").update({
                "status": "completed" if jobs_created == 0 else "pending",
                "started_at": datetime.now().isoformat(),
                "completed_at": datetime.now().isoformat() if jobs_created == 0 else None
            }).eq("id", run_id).execute()
            
            if not CELERY_ENABLED:
                print("⚠ Celery not available - jobs created but not processing automatically")
                print("  Please ensure Celery worker is running to process the jobs")
            elif not repos:
                print("ℹ No teams queued for analysis (all teams analyzed recently or no teams in batch)")
        
        return {
            "run_id": run_id,
            "run_number": run_number,
            "status": "running" if jobs_created > 0 else "skipped",
            "total_teams": total_teams,
            "jobs_created": jobs_created,
            "jobs_skipped": jobs_skipped,
            "skipped_reasons": skipped_reasons[:10] if skipped_reasons else [],  # Limit to first 10
            "message": f"Batch analysis run {run_number}: {jobs_created} teams queued, {jobs_skipped} skipped (already analyzed within interval)"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger batch analysis: {str(e)}"
        )


@router.get(
    "/{batch_id}/runs"
)
async def get_batch_analysis_runs(
    batch_id: UUID,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Get all analysis runs for a batch
    
    Returns list of weekly analysis runs with statistics.
    
    **Permissions:** Authenticated users
    """
    try:
        supabase = get_supabase_admin_client()
        
        # Check if batch exists
        batch_result = supabase.table("batches")\
            .select("id")\
            .eq("id", str(batch_id))\
            .execute()
        
        if not batch_result.data or len(batch_result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Batch not found"
            )
        
        # Get all runs for this batch
        runs_result = supabase.table("batch_analysis_runs")\
            .select("*")\
            .eq("batch_id", str(batch_id))\
            .order("run_number", desc=True)\
            .execute()
        
        runs = runs_result.data or []
        
        return {
            "batch_id": str(batch_id),
            "runs": runs,
            "total_runs": len(runs)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch batch runs: {str(e)}"
        )


@router.get(
    "/{batch_id}/progress"
)
async def get_batch_progress(
    batch_id: UUID,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Get current analysis run progress for a batch
    
    Returns status of the most recent analysis run (for UI polling).
    
    **Permissions:** Authenticated users
    """
    try:
        supabase = get_supabase_admin_client()
        
        # Check if batch exists
        batch_result = supabase.table("batches")\
            .select("id, name")\
            .eq("id", str(batch_id))\
            .execute()
        
        if not batch_result.data or len(batch_result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Batch not found"
            )
        
        # Get most recent run
        runs_result = supabase.table("batch_analysis_runs")\
            .select("*")\
            .eq("batch_id", str(batch_id))\
            .order("run_number", desc=True)\
            .limit(1)\
            .execute()
        
        if not runs_result.data or len(runs_result.data) == 0:
            # No runs yet
            return {
                "status": "pending",
                "processed_teams": 0,
                "total_teams": 0,
                "current_team": None,
                "start_time": None,
                "end_time": None,
                "successful_analyses": 0,
                "failed_analyses": 0
            }
        
        latest_run = runs_result.data[0]
        
        # Determine status based on run data
        status_map = {
            "pending": "pending",
            "running": "in_progress",
            "completed": "completed",
            "failed": "failed"
        }
        
        status = status_map.get(latest_run["status"], "pending")
        
        # Get current job being processed (if any)
        current_team_name = None
        if status == "in_progress":
            current_job = supabase.table("analysis_jobs")\
                .select("teams(team_name)")\
                .eq("status", "processing")\
                .eq("batch_id", str(batch_id))\
                .limit(1)\
                .execute()
            
            if current_job.data and len(current_job.data) > 0:
                teams_data = current_job.data[0].get("teams")
                if teams_data:
                    current_team_name = teams_data.get("team_name") if isinstance(teams_data, dict) else None
        
        return {
            "status": status,
            "processed_teams": latest_run["completed_teams"] + latest_run["failed_teams"],
            "total_teams": latest_run["total_teams"],
            "current_team": current_team_name,
            "start_time": latest_run.get("started_at"),
            "end_time": latest_run.get("completed_at"),
            "successful_analyses": latest_run["completed_teams"],
            "failed_analyses": latest_run["failed_teams"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch batch progress: {str(e)}"
        )


@router.post(
    "/{batch_id}/cancel",
    dependencies=[Depends(RoleChecker(["admin"]))]
)
async def cancel_batch_analysis(
    batch_id: UUID,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Cancel all running analysis tasks for a batch (Admin only)
    
    This will:
    - Revoke all running Celery tasks for this batch
    - Mark all queued/running jobs as cancelled
    - Update batch analysis run status to cancelled
    
    **Permissions:** Admin only
    """
    try:
        from celery_app import celery_app
        
        supabase = get_supabase_admin_client()
        
        # Check if batch exists
        batch_result = supabase.table("batches")\
            .select("id, name")\
            .eq("id", str(batch_id))\
            .execute()
        
        if not batch_result.data or len(batch_result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Batch not found"
            )
        
        batch_name = batch_result.data[0].get("name", "Unknown")
        
        # Get all running/queued analysis jobs for teams in this batch
        teams_response = supabase.table("teams").select("id").eq("batch_id", str(batch_id)).execute()
        team_ids = [t["id"] for t in (teams_response.data or [])]
        
        cancelled_count = 0
        revoked_tasks = []
        
        if team_ids:
            # Get all active jobs
            jobs_response = supabase.table("analysis_jobs")\
                .select("id, metadata")\
                .in_("team_id", team_ids)\
                .in_("status", ["queued", "running"])\
                .execute()
            
            for job in (jobs_response.data or []):
                job_id = job["id"]
                metadata = job.get("metadata", {})
                celery_task_id = metadata.get("celery_task_id")
                
                # Revoke Celery task if it exists
                if celery_task_id:
                    try:
                        celery_app.control.revoke(celery_task_id, terminate=True, signal='SIGKILL')
                        revoked_tasks.append(celery_task_id)
                    except Exception as e:
                        print(f"Failed to revoke task {celery_task_id}: {e}")
                
                # Update job status to cancelled
                supabase.table("analysis_jobs").update({
                    "status": "cancelled",
                    "error_message": f"Cancelled by admin: {current_user.email}",
                    "completed_at": datetime.now().isoformat()
                }).eq("id", job_id).execute()
                
                cancelled_count += 1
        
        # Update batch analysis runs
        runs_response = supabase.table("batch_analysis_runs")\
            .select("id, metadata")\
            .eq("batch_id", str(batch_id))\
            .in_("status", ["pending", "running"])\
            .execute()
        
        for run in (runs_response.data or []):
            run_id = run["id"]
            metadata = run.get("metadata", {})
            celery_task_id = metadata.get("celery_task_id")
            
            # Revoke batch task if it exists
            if celery_task_id:
                try:
                    celery_app.control.revoke(celery_task_id, terminate=True, signal='SIGKILL')
                    revoked_tasks.append(celery_task_id)
                except Exception as e:
                    print(f"Failed to revoke batch task {celery_task_id}: {e}")
            
            # Update run status
            supabase.table("batch_analysis_runs").update({
                "status": "cancelled",
                "completed_at": datetime.now().isoformat()
            }).eq("id", run_id).execute()
        
        return {
            "message": f"Cancelled analysis for batch: {batch_name}",
            "cancelled_jobs": cancelled_count,
            "revoked_celery_tasks": len(revoked_tasks),
            "batch_id": str(batch_id)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel batch analysis: {str(e)}"
        )


@router.post(
    "/{batch_id}/pause",
    dependencies=[Depends(RoleChecker(["admin"]))]
)
async def pause_batch_analysis(
    batch_id: UUID,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Gracefully pause batch analysis after current repository completes (Admin only)
    
    This will:
    - Mark the batch analysis run as "paused"
    - Allow the current repository analysis to complete
    - Stop queuing new repositories
    - Can be resumed later with /resume endpoint
    
    **Permissions:** Admin only
    """
    try:
        supabase = get_supabase_admin_client()
        
        # Check if batch exists
        batch_result = supabase.table("batches")\
            .select("id, name")\
            .eq("id", str(batch_id))\
            .execute()
        
        if not batch_result.data or len(batch_result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Batch not found"
            )
        
        batch_name = batch_result.data[0].get("name", "Unknown")
        
        # Get the most recent running batch analysis run
        runs_response = supabase.table("batch_analysis_runs")\
            .select("id, run_number, status, metadata")\
            .eq("batch_id", str(batch_id))\
            .in_("status", ["pending", "running"])\
            .order("run_number", desc=True)\
            .limit(1)\
            .execute()
        
        if not runs_response.data or len(runs_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active batch analysis run to pause"
            )
        
        run = runs_response.data[0]
        run_id = run["id"]
        
        # Update run status to paused
        # Get existing metadata first
        existing_metadata = run.get("metadata", {}) or {}
        
        # Merge with new pause info
        updated_metadata = {
            **existing_metadata,
            "paused_at": datetime.now().isoformat(),
            "paused_by": current_user.email
        }
        
        supabase.table("batch_analysis_runs").update({
            "status": "paused",
            "metadata": updated_metadata
        }).eq("id", run_id).execute()
        
        return {
            "message": f"Batch analysis paused for: {batch_name}",
            "run_id": run_id,
            "run_number": run["run_number"],
            "note": "Current repository will complete. Analysis will stop after that.",
            "batch_id": str(batch_id)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause batch analysis: {str(e)}"
        )


@router.post(
    "/{batch_id}/resume",
    dependencies=[Depends(RoleChecker(["admin"]))]
)
async def resume_batch_analysis(
    batch_id: UUID,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Resume a paused batch analysis (Admin only)
    
    This will:
    - Resume the paused batch analysis run
    - Continue processing remaining repositories
    
    **Permissions:** Admin only
    """
    try:
        # Import Celery task (may fail if in separate container, but that's OK)
        try:
            from celery_worker import resume_batch_analysis_task
            CELERY_ENABLED = True
        except ImportError:
            # Try importing from celery_app instead (works across containers)
            try:
                from celery_app import celery_app
                resume_batch_analysis_task = celery_app.signature('celery_worker.resume_batch_analysis_task')
                CELERY_ENABLED = True
            except:
                CELERY_ENABLED = False
        
        supabase = get_supabase_admin_client()
        
        # Check if batch exists
        batch_result = supabase.table("batches")\
            .select("id, name")\
            .eq("id", str(batch_id))\
            .execute()
        
        if not batch_result.data or len(batch_result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Batch not found"
            )
        
        batch_name = batch_result.data[0].get("name", "Unknown")
        
        # Get the most recent paused batch analysis run
        runs_response = supabase.table("batch_analysis_runs")\
            .select("id, run_number, metadata")\
            .eq("batch_id", str(batch_id))\
            .eq("status", "paused")\
            .order("run_number", desc=True)\
            .limit(1)\
            .execute()
        
        if not runs_response.data or len(runs_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No paused batch analysis run to resume"
            )
        
        run = runs_response.data[0]
        run_id = run["id"]
        
        # Check if batch was paused recently (within 120 seconds)
        metadata = run.get("metadata", {})
        paused_at_str = metadata.get("paused_at")
        
        if paused_at_str:
            try:
                # Parse the paused_at timestamp
                if paused_at_str.endswith('Z'):
                    paused_at_str = paused_at_str[:-1] + '+00:00'
                paused_at = datetime.fromisoformat(paused_at_str)
                
                # Calculate time since pause (use timezone-naive comparison)
                now = datetime.now()
                if paused_at.tzinfo is not None:
                    # Convert to naive datetime for comparison
                    paused_at = paused_at.replace(tzinfo=None)
                
                time_since_pause = (now - paused_at).total_seconds()
                
                if time_since_pause < 120:
                    remaining_time = int(120 - time_since_pause)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Please wait {remaining_time} seconds before resuming. This allows current jobs to complete gracefully."
                    )
            except (ValueError, AttributeError):
                # If datetime parsing fails, allow resume
                pass
        
        # Get all teams that haven't been analyzed yet in this run
        teams_result = supabase.table("teams")\
            .select("id, team_name, repo_url")\
            .eq("batch_id", str(batch_id))\
            .execute()
        
        teams = teams_result.data or []
        
        # Get jobs that are already completed/failed in this run
        jobs_result = supabase.table("analysis_jobs")\
            .select("team_id, status")\
            .eq("metadata->>batch_run_id", run_id)\
            .execute()
        
        completed_team_ids = set(
            job["team_id"] for job in (jobs_result.data or [])
            if job["status"] in ["completed", "failed", "cancelled"]
        )
        
        # Build list of remaining repos to process
        repos = []
        for team in teams:
            if team["id"] not in completed_team_ids and team.get("repo_url"):
                # Create new analysis job for this team
                job_insert = {
                    "team_id": team["id"],
                    "status": "queued",
                    "requested_by": str(current_user.user_id),
                    "started_at": datetime.now().isoformat(),
                    "metadata": {
                        "batch_run_id": run_id,
                        "run_number": run["run_number"],
                        "resumed": True
                    }
                }
                
                job_result = supabase.table("analysis_jobs").insert(job_insert).execute()
                job_id = job_result.data[0]["id"]
                
                repos.append({
                    "team_id": team["id"],
                    "job_id": job_id,
                    "repo_url": team["repo_url"],
                    "team_name": team["team_name"]
                })
        
        if not repos:
            # No remaining repos to process
            supabase.table("batch_analysis_runs").update({
                "status": "completed",
                "completed_at": datetime.now().isoformat()
            }).eq("id", run_id).execute()
            
            return {
                "message": f"No remaining repositories to process for: {batch_name}",
                "run_id": run_id,
                "batch_id": str(batch_id)
            }
        
        # Update run status to running
        supabase.table("batch_analysis_runs").update({
            "status": "running",
            "metadata": {
                **run.get("metadata", {}),
                "resumed_at": datetime.now().isoformat(),
                "resumed_by": current_user.email
            }
        }).eq("id", run_id).execute()
        
        # Queue Celery task to process remaining repos
        if CELERY_ENABLED:
            try:
                if callable(resume_batch_analysis_task):
                    # Direct import worked
                    task = resume_batch_analysis_task.delay(str(batch_id), run_id, repos)
                else:
                    # Using signature (cross-container)
                    task = resume_batch_analysis_task.apply_async(args=[str(batch_id), run_id, repos])
                
                # Store Celery task ID
                supabase.table("batch_analysis_runs").update({
                    "metadata": {
                        **run.get("metadata", {}),
                        "celery_task_id": task.id,
                        "resumed_at": datetime.now().isoformat(),
                        "resumed_by": current_user.email
                    }
                }).eq("id", run_id).execute()
            except Exception as celery_error:
                print(f"⚠ Celery queueing failed: {celery_error}")
                print(f"  Error type: {type(celery_error).__name__}")
                import traceback
                traceback.print_exc()
                print("  Marking jobs as failed due to Celery unavailability...")
                
                # CRITICAL FIX: Mark all newly created jobs as failed
                try:
                    for repo in repos:
                        job_id = repo.get('job_id')
                        team_id = repo.get('team_id')
                        
                        if job_id:
                            supabase.table("analysis_jobs").update({
                                "status": "failed",
                                "error_message": f"Celery task submission failed: {str(celery_error)}",
                                "completed_at": datetime.now().isoformat()
                            }).eq("id", job_id).execute()
                        
                        # Reset team status
                        if team_id:
                            supabase.table("teams").update({
                                "status": "pending"
                            }).eq("id", team_id).execute()
                    
                    print(f"  ✓ Marked {len(repos)} jobs as failed")
                    
                except Exception as cleanup_error:
                    print(f"  ❌ Failed to cleanup jobs: {cleanup_error}")
                
                # Mark batch run as failed
                supabase.table("batch_analysis_runs").update({
                    "status": "failed",
                    "metadata": {
                        **run.get("metadata", {}),
                        "error": f"Celery unavailable: {str(celery_error)}"
                    }
                }).eq("id", run_id).execute()
                
                # Raise HTTP exception
                raise HTTPException(
                    status_code=503,
                    detail=f"Analysis service unavailable: {str(celery_error)}"
                )
        
        return {
            "message": f"Batch analysis resumed for: {batch_name}",
            "run_id": run_id,
            "run_number": run["run_number"],
            "remaining_repos": len(repos),
            "batch_id": str(batch_id)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume batch analysis: {str(e)}"
        )


@router.delete(
    "/{batch_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RoleChecker(["admin"]))]
)
async def delete_batch(
    batch_id: UUID,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Delete batch (Admin only)
    
    **Warning:** This will CASCADE DELETE ALL related data:
    - All teams in the batch
    - All analysis jobs (including running jobs)
    - All analysis snapshots
    - All issues
    - All tech stack entries
    - All team members
    - All project comments
    - All mentor assignments
    - All students
    - All batch analysis runs
    
    **Note:** Running Celery tasks will be cancelled automatically
    
    **Permissions:** Admin only
    """
    try:
        from celery_app import celery_app
        
        supabase = get_supabase_admin_client()
        
        # Check if batch exists
        existing = supabase.table("batches")\
            .select("id")\
            .eq("id", str(batch_id))\
            .execute()
        
        if not existing.data or len(existing.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Batch not found"
            )
        
        # Get all teams in this batch
        teams_response = supabase.table("teams").select("id").eq("batch_id", str(batch_id)).execute()
        teams_data = teams_response.data or []
        team_ids = [team.get("id") for team in teams_data if team.get("id")]

        # Cancel all running Celery tasks for this batch
        if team_ids:
            # Get all active jobs and cancel their Celery tasks
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
        
        # Cancel batch-level Celery tasks
        runs_response = supabase.table("batch_analysis_runs")\
            .select("id, metadata")\
            .eq("batch_id", str(batch_id))\
            .in_("status", ["pending", "running"])\
            .execute()
        
        for run in (runs_response.data or []):
            metadata = run.get("metadata", {})
            celery_task_id = metadata.get("celery_task_id")
            
            if celery_task_id:
                try:
                    celery_app.control.revoke(celery_task_id, terminate=True, signal='SIGKILL')
                except Exception as e:
                    print(f"Failed to revoke batch task {celery_task_id}: {e}")

        if team_ids:
            # Delete all related data for these teams
            # Order matters: delete child records before parent records
            
            # 1. Delete analysis-related data
            supabase.table("analysis_jobs").delete().in_("team_id", team_ids).execute()
            supabase.table("analysis_snapshots").delete().in_("team_id", team_ids).execute()
            
            # 2. Delete team-related data
            supabase.table("issues").delete().in_("team_id", team_ids).execute()
            supabase.table("project_comments").delete().in_("team_id", team_ids).execute()
            supabase.table("tech_stack").delete().in_("team_id", team_ids).execute()
            supabase.table("team_members").delete().in_("team_id", team_ids).execute()
            
            # 3. Delete assignments
            supabase.table("mentor_team_assignments").delete().in_("team_id", team_ids).execute()
            supabase.table("students").delete().in_("team_id", team_ids).execute()
            
            # 4. Delete teams themselves
            supabase.table("teams").delete().in_("id", team_ids).execute()
        
        # Delete batch analysis runs
        supabase.table("batch_analysis_runs").delete().eq("batch_id", str(batch_id)).execute()
        
        # Delete the batch itself
        supabase.table("batches").delete().eq("id", str(batch_id)).execute()
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete batch: {str(e)}"
        )
