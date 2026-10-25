import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_admin
from app.schemas.common import ok, err
from app.schemas.communication import (
    ScheduleCommunicationRequest,
    ScheduleSequenceRequest,
    SendCommunicationRequest,
)
from app.services.communication_service import (
    CommunicationService,
    list_segments,
    list_templates,
)
from app.services.communication_scheduler import CommunicationScheduler, serialize

router = APIRouter(prefix="/api/admin/communication", tags=["Communication"])


@router.get("/templates")
async def get_templates(admin=Depends(get_current_admin)):
    """The canonical PMS lifecycle templates (kickoff, team-formation, etc.)."""
    return ok(data=list_templates())


@router.get("/segments")
async def get_segments(admin=Depends(get_current_admin)):
    """The audience segments the agent can resolve (for the recipient dropdown)."""
    return ok(data=list_segments())


@router.post("/send")
async def send_communication(
    payload: SendCommunicationRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Resolve the audience, render the template, send, and log."""
    try:
        result = await CommunicationService.send(
            db,
            subject=payload.subject,
            body=payload.body,
            template_code=payload.template_code,
            segment=payload.segment,
            context=payload.context,
            admin_id=admin.id,
            semester_id=payload.semester_id,
            team_id=payload.team_id,
        )
    except ValueError as e:
        return err("VALIDATION_ERROR", str(e))
    except Exception as e:
        return err("ACTION_FAILED", f"Could not send communication: {str(e)}")

    return ok(data=result, message=f"Sent to {result['sent']} recipient(s)")


@router.get("/history")
async def get_history(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return ok(data=await CommunicationService.history(db, limit=limit))


# ----------------------------------------------------------------------------- #
# Scheduling — fire communications automatically at a future time
# ----------------------------------------------------------------------------- #
@router.post("/schedule")
async def schedule_communication(
    payload: ScheduleCommunicationRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Queue one communication to auto-send at ``send_at``."""
    try:
        row = await CommunicationScheduler.schedule(
            db,
            send_at=payload.send_at,
            segment=payload.segment,
            template_code=payload.template_code,
            subject=payload.subject,
            body=payload.body,
            context=payload.context,
            team_id=payload.team_id,
            semester_id=payload.semester_id,
            created_by=admin.id,
        )
    except ValueError as e:
        return err("VALIDATION_ERROR", str(e))
    return ok(data=serialize(row), message="Communication scheduled")


@router.post("/schedule-sequence")
async def schedule_sequence(
    payload: ScheduleSequenceRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Queue a multi-step trigger sequence (e.g. kickoff now, team-formation +3d)."""
    try:
        rows = await CommunicationScheduler.schedule_sequence(
            db,
            [s.model_dump() for s in payload.steps],
            base=payload.base,
            semester_id=payload.semester_id,
            created_by=admin.id,
        )
    except ValueError as e:
        return err("VALIDATION_ERROR", str(e))
    return ok(data=[serialize(r) for r in rows], message=f"{len(rows)} step(s) scheduled")


@router.get("/scheduled")
async def list_scheduled(
    status: str = "pending",
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    rows = await CommunicationScheduler.list_scheduled(db, status=status or None)
    return ok(data=[serialize(r) for r in rows])


@router.post("/scheduled/{sched_id}/cancel")
async def cancel_scheduled(
    sched_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    cancelled = await CommunicationScheduler.cancel(db, sched_id)
    if not cancelled:
        return err("NOT_FOUND", "No pending scheduled communication with that id", 404)
    return ok(data={"id": str(sched_id), "status": "cancelled"}, message="Schedule cancelled")


@router.post("/run-due")
async def run_due(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Manually fire anything currently due (the background poller does this on a
    timer; this endpoint is for on-demand dispatch and demos)."""
    summary = await CommunicationScheduler.run_due(db)
    return ok(data=summary, message=f"Fired {summary['fired']} of {summary['due']} due")


# Map the admin UI's free-text target labels onto agent segment keys.
_TARGET_TO_SEGMENT = {
    "All Students": "all_students",
    "All Enrolled Students": "all_students",
    "Team Leaders": "team_leaders",
    "Faculty Mentors": "mentors",
    "Unassigned Teams": "teams_without_mentors",
    "Teams without Mentors": "teams_without_mentors",
    "Unallocated Students": "unassigned_students",
}


@router.post("/broadcast")
async def broadcast_mail(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Backwards-compatible broadcast — now actually resolves + sends instead of
    just simulating success. Accepts the old ``{template_name, target_group,
    subject, body}`` shape."""
    target_group = payload.get("target_group") or payload.get("recipients")
    segment = _TARGET_TO_SEGMENT.get(target_group, target_group)
    subject = payload.get("subject") or payload.get("template_name")
    body = payload.get("body")

    try:
        result = await CommunicationService.send(
            db,
            subject=subject,
            body=body,
            segment=segment,
            context=payload.get("context", {}),
            admin_id=admin.id,
            team_id=payload.get("team_id"),
            semester_id=payload.get("semester_id"),
        )
    except ValueError as e:
        return err("VALIDATION_ERROR", str(e))
    except Exception as e:
        return err("ACTION_FAILED", f"Could not broadcast: {str(e)}")

    return ok(
        data={"sent": result["sent"], "target": target_group, "recipients": result["recipients"]},
        message=f"Broadcast sent to {result['sent']} recipient(s)",
    )
