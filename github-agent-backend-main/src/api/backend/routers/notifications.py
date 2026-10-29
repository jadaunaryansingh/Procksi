"""
Notifications API endpoints for admin dashboard.
Provides in-app notification bell functionality.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..middleware.auth import get_current_user, AuthUser
from ..database import get_supabase_admin_client


router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


# ── Response Models ──────────────────────────────────────────────

class NotificationOut(BaseModel):
    id: str
    type: str
    title: str
    message: str
    metadata: dict
    is_read: bool
    created_at: str


class UnreadCountResponse(BaseModel):
    count: int


# ── Endpoints ────────────────────────────────────────────────────

@router.get("")
async def list_notifications(
    unread_only: bool = Query(False, description="Only return unread notifications"),
    limit: int = Query(50, ge=1, le=100),
    current_user: AuthUser = Depends(get_current_user),
):
    """List recent notifications for the admin dashboard."""
    if current_user.role.lower() not in ("admin", "mentor"):
        raise HTTPException(status_code=403, detail="Not authorized")

    supabase = get_supabase_admin_client()
    query = supabase.table("notifications").select("*").order("created_at", desc=True).limit(limit)

    if unread_only:
        query = query.eq("is_read", False)

    result = query.execute()
    return {"notifications": result.data or []}


@router.get("/unread-count")
async def get_unread_count(
    current_user: AuthUser = Depends(get_current_user),
):
    """Get the count of unread notifications (for badge display)."""
    if current_user.role.lower() not in ("admin", "mentor"):
        raise HTTPException(status_code=403, detail="Not authorized")

    supabase = get_supabase_admin_client()
    result = (
        supabase.table("notifications")
        .select("id", count="exact")
        .eq("is_read", False)
        .execute()
    )
    return {"count": result.count or 0}


@router.patch("/{notification_id}/read")
async def mark_as_read(
    notification_id: str,
    current_user: AuthUser = Depends(get_current_user),
):
    """Mark a single notification as read."""
    if current_user.role.lower() not in ("admin", "mentor"):
        raise HTTPException(status_code=403, detail="Not authorized")

    supabase = get_supabase_admin_client()
    result = (
        supabase.table("notifications")
        .update({"is_read": True})
        .eq("id", notification_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}


@router.patch("/read-all")
async def mark_all_as_read(
    current_user: AuthUser = Depends(get_current_user),
):
    """Mark all notifications as read."""
    if current_user.role.lower() not in ("admin", "mentor"):
        raise HTTPException(status_code=403, detail="Not authorized")

    supabase = get_supabase_admin_client()
    supabase.table("notifications").update({"is_read": True}).eq("is_read", False).execute()
    return {"success": True}


@router.post("/send-student-reports")
async def send_student_reports(
    test_email: Optional[str] = Query(None, description="If provided, send exactly one test email to this address"),
    current_user: AuthUser = Depends(get_current_user),
):
    """Manually trigger weekly PDF report emails to students. Admin only."""
    if current_user.role.lower() != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    from celery_worker import send_weekly_student_reports

    if test_email:
        test_email = test_email.strip()
        if "@" not in test_email:
            raise HTTPException(status_code=400, detail="Invalid test_email")

        send_weekly_student_reports.delay(test_email=test_email, max_emails=1)
        return {
            "success": True,
            "message": f"Single test report email queued for {test_email}. Check notifications for progress."
        }

    # Check if a run is already active to prevent duplicate sends
    from celery_worker import is_weekly_reports_already_running
    lock_check = is_weekly_reports_already_running()
    if lock_check['running']:
        raise HTTPException(
            status_code=409,
            detail=(
                f"A weekly reports run is already in progress "
                f"(started {lock_check.get('started_at', 'unknown')}). "
                f"Please wait for it to complete before triggering another."
            )
        )

    send_weekly_student_reports.delay()
    return {"success": True, "message": "Student report emails queued. Check notifications for progress."}


# ── Email Send Log Endpoints ─────────────────────────────────────

@router.get("/email-log")
async def list_email_send_log(
    task_run_id: Optional[str] = Query(None, description="Filter by task run ID"),
    notification_id: Optional[str] = Query(None, description="Filter by notification ID"),
    status: Optional[str] = Query(None, description="Filter by status: sent, failed"),
    team_id: Optional[str] = Query(None, description="Filter by team ID"),
    batch_id: Optional[str] = Query(None, description="Filter by batch ID"),
    student_email: Optional[str] = Query(None, description="Filter by student email"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
):
    """Query the email_send_log table. Admin only."""
    if current_user.role.lower() != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    supabase = get_supabase_admin_client()
    query = (
        supabase.table("email_send_log")
        .select("*", count="exact")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )

    if task_run_id:
        query = query.eq("task_run_id", task_run_id)
    if notification_id:
        query = query.eq("notification_id", notification_id)
    if status:
        query = query.eq("status", status)
    if team_id:
        query = query.eq("team_id", team_id)
    if batch_id:
        query = query.eq("batch_id", batch_id)
    if student_email:
        query = query.eq("student_email", student_email)

    result = query.execute()
    return {
        "logs": result.data or [],
        "total": result.count or 0,
        "limit": limit,
        "offset": offset,
    }


@router.get("/email-log/summary")
async def email_send_log_summary(
    batch_id: Optional[str] = Query(None, description="Filter by batch ID"),
    task_run_id: Optional[str] = Query(None, description="Filter by task run ID"),
    notification_id: Optional[str] = Query(None, description="Filter by notification ID"),
    current_user: AuthUser = Depends(get_current_user),
):
    """Get aggregated summary of email sends. Admin only."""
    if current_user.role.lower() != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    supabase = get_supabase_admin_client()

    # Get sent count
    sent_query = supabase.table("email_send_log").select("id", count="exact").eq("status", "sent")
    failed_query = supabase.table("email_send_log").select("id", count="exact").eq("status", "failed")

    if batch_id:
        sent_query = sent_query.eq("batch_id", batch_id)
        failed_query = failed_query.eq("batch_id", batch_id)
    if task_run_id:
        sent_query = sent_query.eq("task_run_id", task_run_id)
        failed_query = failed_query.eq("task_run_id", task_run_id)
    if notification_id:
        sent_query = sent_query.eq("notification_id", notification_id)
        failed_query = failed_query.eq("notification_id", notification_id)

    sent_result = sent_query.execute()
    failed_result = failed_query.execute()

    # Get recent runs (distinct task_run_ids)
    recent_runs_query = (
        supabase.table("email_send_log")
        .select("task_run_id, notification_id, email_type, created_at")
        .order("created_at", desc=True)
        .limit(500)
    )
    if batch_id:
        recent_runs_query = recent_runs_query.eq("batch_id", batch_id)
    recent_runs_result = recent_runs_query.execute()

    # Group by task_run_id
    runs = {}
    for row in (recent_runs_result.data or []):
        rid = row.get("task_run_id")
        if rid and rid not in runs:
            runs[rid] = {
                "task_run_id": rid,
                "notification_id": row.get("notification_id"),
                "email_type": row.get("email_type"),
                "earliest": row.get("created_at"),
            }

    return {
        "total_sent": sent_result.count or 0,
        "total_failed": failed_result.count or 0,
        "recent_runs": list(runs.values())[:20],
    }
