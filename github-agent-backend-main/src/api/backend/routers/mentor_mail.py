"""
Mentor Mail API – custom email from mentor/admin to a team's students.

Endpoints:
  POST /api/mentor-mail/team/{team_id}    – compose & send a custom email
  GET  /api/mentor-mail/team/{team_id}    – list sent emails for a team
  GET  /api/mentor-mail/sent              – list all emails sent by the current user
"""
from datetime import datetime
from typing import List, Optional
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from ..middleware.auth import get_current_user, AuthUser
from ..database import get_supabase_admin_client
from ..crud import TeamCRUD
from ..utils.email import send_alert_email, EmailConfigError
from ..templates.email_templates import EmailTemplates

router = APIRouter(prefix="/api/mentor-mail", tags=["Mentor Mail"])


# ── Request / Response Models ────────────────────────────────────────────

class ComposeMailRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1, max_length=10000)
    cc_emails: List[str] = Field(default_factory=list, description="Optional CC addresses")


class ComposeMailResponse(BaseModel):
    id: str
    sent: int
    failed: int
    skipped: int


class SentMailItem(BaseModel):
    id: str
    team_id: str
    team_name: Optional[str] = None
    subject: str
    body: str
    recipients: list = []
    cc_emails: list = []
    send_status: str = "sent"
    emails_sent: int = 0
    emails_failed: int = 0
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    created_at: str


class SentMailListResponse(BaseModel):
    emails: List[SentMailItem]
    total: int


# ── Helpers ──────────────────────────────────────────────────────────────

def _ensure_mentor_or_admin(current_user: AuthUser, team_id: str) -> None:
    """Verify the caller is an admin or the assigned mentor for the team."""
    role = current_user.role.lower()
    if role == "admin":
        return
    if role != "mentor":
        raise HTTPException(status_code=403, detail="Only mentors or admins can send team emails")
    mentor_id = str(current_user.user_id)
    team_ids = TeamCRUD.get_mentor_team_ids(mentor_id)
    if team_id not in team_ids:
        raise HTTPException(status_code=403, detail="You are not assigned to this team")


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/team/{team_id}", response_model=ComposeMailResponse)
async def send_team_mail(
    payload: ComposeMailRequest,
    team_id: str = Path(..., description="Team UUID"),
    current_user: AuthUser = Depends(get_current_user),
):
    """
    Send a custom email to all students in a team.
    The mentor's email is set as Reply-To so students can reply directly.
    """
    _ensure_mentor_or_admin(current_user, team_id)

    supabase = get_supabase_admin_client()

    # Fetch team info
    team_resp = supabase.table("teams").select("id, team_name, batch_id").eq("id", team_id).limit(1).execute()
    if not team_resp.data:
        raise HTTPException(status_code=404, detail="Team not found")
    team = team_resp.data[0]

    # Fetch students
    students_resp = supabase.table("students").select("id, email, name").eq("team_id", team_id).execute()
    students = students_resp.data or []
    if not students:
        raise HTTPException(status_code=400, detail="No students found in this team")

    sender_email = current_user.email
    sender_name = current_user.full_name or sender_email
    brand = os.getenv("SMTP_FROM_NAME", "ProjectFlow")

    sent = 0
    failed = 0
    skipped = 0
    recipient_list: List[str] = []

    # Build HTML email via template
    html_body = EmailTemplates.mentor_custom_mail_html(
        sender_name=sender_name,
        team_name=team.get("team_name", ""),
        subject=payload.subject,
        body=payload.body,
    )

    for student in students:
        email_addr = student.get("email")
        student_name = student.get("name", "")
        if not email_addr:
            skipped += 1
            continue
        try:
            send_alert_email(
                subject=f"{brand}: {payload.subject}",
                body_text=f"From: {sender_name}\nTeam: {team.get('team_name', '')}\n\n{payload.body}",
                to_email=email_addr,
                reply_to=sender_email,
                bcc=[sender_email] if sent == 0 else None,  # BCC sender on first email only
                html_body=html_body,
            )
            recipient_list.append(email_addr)
            
            # Log to email_send_log for dashboard tracking
            try:
                supabase.table("email_send_log").insert({
                    "team_id": team_id,
                    "team_name": team.get("team_name"),
                    "student_name": student_name,
                    "student_email": email_addr,
                    "batch_id": team.get("batch_id"),
                    "status": "sent",
                    "email_type": "mentor_custom",
                    "subject": payload.subject,
                    "sent_at": datetime.utcnow().isoformat(),
                }).execute()
            except Exception as log_err:
                # Don't fail the email send if logging fails
                pass
            
            sent += 1
        except (EmailConfigError, Exception) as exc:
            failed += 1
            
            # Log failed email to email_send_log
            try:
                supabase.table("email_send_log").insert({
                    "team_id": team_id,
                    "team_name": team.get("team_name"),
                    "student_name": student_name,
                    "student_email": email_addr,
                    "batch_id": team.get("batch_id"),
                    "status": "failed",
                    "email_type": "mentor_custom",
                    "subject": payload.subject,
                    "error_message": str(exc)[:1000],
                }).execute()
            except Exception as log_err:
                # Don't fail the email send if logging fails
                pass

    # Determine overall status
    if sent == 0 and failed > 0:
        status = "failed"
    elif failed > 0:
        status = "partial"
    else:
        status = "sent"

    # Persist to mentor_emails table
    row = {
        "team_id": team_id,
        "sender_id": str(current_user.user_id),
        "sender_email": sender_email,
        "sender_name": sender_name,
        "subject": payload.subject,
        "body": payload.body,
        "recipients": recipient_list,
        "cc_emails": payload.cc_emails,
        "send_status": status,
        "emails_sent": sent,
        "emails_failed": failed,
    }
    insert_resp = supabase.table("mentor_emails").insert(row).execute()
    record_id = insert_resp.data[0]["id"] if insert_resp.data else ""

    return ComposeMailResponse(id=record_id, sent=sent, failed=failed, skipped=skipped)


@router.get("/team/{team_id}", response_model=SentMailListResponse)
async def get_team_mail_history(
    team_id: str = Path(..., description="Team UUID"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
):
    """List all custom emails sent to a team (visible to assigned mentor & admins)."""
    _ensure_mentor_or_admin(current_user, team_id)

    supabase = get_supabase_admin_client()

    # Get team name
    team_resp = supabase.table("teams").select("team_name").eq("id", team_id).limit(1).execute()
    team_name = team_resp.data[0]["team_name"] if team_resp.data else None

    resp = (
        supabase.table("mentor_emails")
        .select("*")
        .eq("team_id", team_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )

    count_resp = (
        supabase.table("mentor_emails")
        .select("id", count="exact")
        .eq("team_id", team_id)
        .execute()
    )

    emails = [
        SentMailItem(
            id=str(e["id"]),
            team_id=str(e["team_id"]),
            team_name=team_name,
            subject=e["subject"],
            body=e["body"],
            recipients=e.get("recipients") or [],
            cc_emails=e.get("cc_emails") or [],
            send_status=e.get("send_status", "sent"),
            emails_sent=e.get("emails_sent", 0),
            emails_failed=e.get("emails_failed", 0),
            sender_name=e.get("sender_name"),
            sender_email=e.get("sender_email"),
            created_at=e.get("created_at", ""),
        )
        for e in (resp.data or [])
    ]

    return SentMailListResponse(emails=emails, total=count_resp.count or len(emails))


@router.get("/sent", response_model=SentMailListResponse)
async def get_my_sent_mails(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
):
    """List all custom emails sent by the current mentor/admin."""
    supabase = get_supabase_admin_client()
    sender_id = str(current_user.user_id)

    resp = (
        supabase.table("mentor_emails")
        .select("*, teams(team_name)")
        .eq("sender_id", sender_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )

    count_resp = (
        supabase.table("mentor_emails")
        .select("id", count="exact")
        .eq("sender_id", sender_id)
        .execute()
    )

    emails = [
        SentMailItem(
            id=str(e["id"]),
            team_id=str(e["team_id"]),
            team_name=e.get("teams", {}).get("team_name") if e.get("teams") else None,
            subject=e["subject"],
            body=e["body"],
            recipients=e.get("recipients") or [],
            cc_emails=e.get("cc_emails") or [],
            send_status=e.get("send_status", "sent"),
            emails_sent=e.get("emails_sent", 0),
            emails_failed=e.get("emails_failed", 0),
            sender_name=e.get("sender_name"),
            sender_email=e.get("sender_email"),
            created_at=e.get("created_at", ""),
        )
        for e in (resp.data or [])
    ]

    return SentMailListResponse(emails=emails, total=count_resp.count or len(emails))
