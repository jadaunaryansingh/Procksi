"""
Alerts API endpoints for sending student notifications.
"""
from datetime import datetime
from typing import List, Optional
import os

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from ..middleware.auth import get_current_user, AuthUser
from ..database import get_supabase_admin_client
from ..crud import TeamCRUD
from ..utils.email import send_alert_email, EmailConfigError
from ..templates.email_templates import EmailTemplates


router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


class AlertCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=4000)
    severity: str = Field("info", description="info|warning|critical")
    bcc_sender: bool = True


class AlertCreateResponse(BaseModel):
    sent: int
    failed: int
    skipped: int


def _ensure_role(current_user: AuthUser, team_id: str) -> None:
    role = current_user.role.lower()
    if role == "admin":
        return

    if role != "mentor":
        raise HTTPException(status_code=403, detail="Not authorized to send alerts")

    mentor_id = str(current_user.user_id)
    team_ids = TeamCRUD.get_mentor_team_ids(mentor_id)
    if team_id not in team_ids:
        raise HTTPException(status_code=403, detail="Not authorized to alert this team")


def _build_email_body(title: str, message: str, team_name: Optional[str]) -> dict:
    brand = os.getenv("SMTP_FROM_NAME", "ProjectFlow")
    header = f"{brand} Alert: {title}"
    if team_name:
        header = f"{header} (Team: {team_name})"
    text_body = f"{header}\n\n{message}\n"
    
    severity_color = "#3b82f6"  # default blue for info
    html_content = f"""
    <p style="font-size:14px;">{message}</p>
    """
    if team_name:
        html_content = f"""
        <p>Team: <strong>{team_name}</strong></p>
        <p style="font-size:14px;">{message}</p>
        """
    html_body = EmailTemplates.get_html_wrapper(header, html_content)
    return {"text": text_body, "html": html_body}


@router.post("/team/{team_id}", response_model=AlertCreateResponse)
async def send_team_alert(
    payload: AlertCreateRequest,
    team_id: str = Path(..., description="Team ID"),
    current_user: AuthUser = Depends(get_current_user)
):
    _ensure_role(current_user, team_id)

    severity = payload.severity.lower().strip()
    if severity not in {"info", "warning", "critical"}:
        raise HTTPException(status_code=400, detail="Invalid severity")

    supabase = get_supabase_admin_client()

    team_response = supabase.table("teams").select("id, team_name").eq("id", team_id).limit(1).execute()
    if not team_response.data:
        raise HTTPException(status_code=404, detail="Team not found")
    team = team_response.data[0]

    students_response = supabase.table("students").select("id, email, name").eq("team_id", team_id).execute()
    students = students_response.data or []
    if not students:
        return AlertCreateResponse(sent=0, failed=0, skipped=0)

    sent = 0
    failed = 0
    skipped = 0

    sender_email = current_user.email
    bcc_list: List[str] = [sender_email] if payload.bcc_sender and sender_email else []

    for student in students:
        student_email = student.get("email")
        if not student_email:
            skipped += 1
            continue

        brand = os.getenv("SMTP_FROM_NAME", "ProjectFlow")
        subject = f"{brand} Alert: {payload.title}"
        body = _build_email_body(payload.title, payload.message, team.get("team_name"))
        body_text = body.get("text", "") if isinstance(body, dict) else body
        html_body = body.get("html") if isinstance(body, dict) else None

        send_status = "sent"
        error_text = None
        sent_at = None

        try:
            send_alert_email(
                subject=subject,
                body_text=body_text,
                to_email=student_email,
                reply_to=sender_email,
                bcc=bcc_list or None,
                html_body=html_body,
            )
            sent_at = datetime.utcnow().isoformat()
            sent += 1
        except EmailConfigError as e:
            send_status = "failed"
            error_text = str(e)
            failed += 1
        except Exception as e:
            send_status = "failed"
            error_text = str(e)
            failed += 1

        alert_row = {
            "team_id": team_id,
            "student_id": student.get("id"),
            "recipient_email": student_email,
            "sender_id": str(current_user.user_id),
            "sender_role": current_user.role.lower(),
            "title": payload.title,
            "message": payload.message,
            "severity": severity,
            "send_status": send_status,
            "sent_at": sent_at,
            "error": error_text,
        }
        alert_rows.append(alert_row)

    # Batch-insert all alert log rows in one query
    if alert_rows:
        supabase.table("alerts").insert(alert_rows).execute()

    return AlertCreateResponse(sent=sent, failed=failed, skipped=skipped)
