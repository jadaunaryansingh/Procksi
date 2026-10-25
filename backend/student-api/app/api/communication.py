import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_admin
from app.repositories.email_log_repo import email_log_repo
from app.services.email_service import (
    send_awareness_mail,
    send_proposal_submission_reminder,
    send_team_formation_reminder,
    send_mentor_allocation_notice,
    send_presentation_schedule_notice,
    send_result_announcement,
)
from app.schemas.common import ok, err, StandardResponse
from app.schemas.communication import SendMailRequest

router = APIRouter(prefix="/api/admin/communication", tags=["Communication"])

TEMPLATES_REGISTRY = [
    {"id": "1", "name": "Awareness Campaign", "code": "awareness", "subject": "Project Management System: Getting Started", "body": "Welcome to the PMS..."},
    {"id": "2", "name": "Proposal Submission Reminder", "code": "proposal_reminder", "subject": "URGENT: Project Proposal Deadline", "body": "Please submit your proposal by {deadline}..."},
    {"id": "3", "name": "Team Formation Alert", "code": "team_formation_reminder", "subject": "TEAM FORMATION: Final Call", "body": "Form your teams before the deadline..."},
    {"id": "4", "name": "Mentor Allocation Notice", "code": "mentor_allocation", "subject": "MENTOR ALLOCATED: {team_name}", "body": "Your project team {team_name} has been assigned to {mentor_name}..."},
    {"id": "5", "name": "Presentation Schedule", "code": "presentation_schedule", "subject": "SCHEDULE RELEASED: Presentation Round", "body": "Your presentation is scheduled on {date} at {time_slot} in {room}..."},
    {"id": "6", "name": "Result Announcement", "code": "result_announcement", "subject": "GRADES PUBLISHED: Final Evaluation", "body": "The final results for team {team_name} have been published. Total Score: {total_score}%..."},
]

@router.get("/templates")
async def list_templates(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return ok(data=TEMPLATES_REGISTRY)


@router.post("/broadcast")
async def broadcast_mail(
    payload: dict, # Generic payload from frontend
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    template_name = payload.get("template_name")
    target_group = payload.get("target_group")
    subject = payload.get("subject")
    body = payload.get("body")

    # In a real app, you'd resolve target_group to a list of emails
    # For now, we simulate success for the UI
    
    # Log the email broadcast
    log_in = {
        "subject": subject or template_name,
        "body": body or f"Broadcast to {target_group}",
        "recipients": [f"group:{target_group}"], # Placeholder tag
        "sent_by": str(admin.id),
    }
    await email_log_repo.create(db, obj_in=log_in)

    return ok(
        data={"sent": True, "target": target_group},
        message=f"Broadcast successfully initiated for {target_group}"
    )
