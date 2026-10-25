import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_admin
from app.models.team_member import TeamMember
from app.models.student import Student
from app.schemas.proposal import ProposalActionRequest, ProposalResponse, ProposalCreate
from app.schemas.common import ok, paginated, err
from app.services.proposal_service import ProposalService

router = APIRouter(prefix="/api/admin/proposals", tags=["Proposals"])


@router.post("", response_model=ProposalResponse)
async def create_proposal(
    payload: ProposalCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        proposal = await ProposalService.create_proposal(
            db, 
            team_id=payload.team_id,
            title=payload.title,
            description=payload.description,
            document_url=payload.document_url
        )
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)

    return proposal


@router.get("")
async def list_proposals(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    status: Optional[str] = None,
    semester_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    if not semester_id:
        from app.repositories.semester_repo import semester_repo
        active_sem = await semester_repo.get_active(db)
        if active_sem:
            semester_id = active_sem.id

    proposals, total = await ProposalService.list_proposals(
        db, page, limit, status, semester_id
    )

    return paginated(
        data=[
            {
                "id": p.id,
                "team_id": p.team_id,
                "semester_id": p.semester_id,
                "title": p.title,
                "description": p.description,
                "document_url": p.document_url,
                "ai_score": p.ai_score,
                "status": p.status,
                "submitted_at": p.submitted_at.isoformat(),
            }
            for p in proposals
        ],
        page=page,
        limit=limit,
        total=total,
    )


@router.get("/{proposal_id}")
async def get_proposal(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    from app.repositories.proposal_repo import proposal_repo
    proposal = await proposal_repo.get(db, proposal_id)
    if not proposal:
        return err("NOT_FOUND", "Proposal not found", 404)

    members_result = await db.execute(
        select(TeamMember, Student)
        .join(Student, Student.id == TeamMember.student_id)
        .where(TeamMember.team_id == proposal.team_id)
    )
    members = [
        {
            "student_id": s.student_id,
            "name": s.name,
            "email": s.email,
            "role": tm.role,
        }
        for tm, s in members_result.fetchall()
    ]

    return ok(
        data={
            "id": proposal.id,
            "team_id": proposal.team_id,
            "semester_id": proposal.semester_id,
            "title": proposal.title,
            "description": proposal.description,
            "document_url": proposal.document_url,
            "ai_score": proposal.ai_score,
            "status": proposal.status,
            "submitted_at": proposal.submitted_at.isoformat(),
            "team_members": members,
        }
    )


@router.post("/approve")
async def approve_proposal(
    payload: ProposalActionRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        proposal = await ProposalService.update_status(db, payload.proposal_id, "approved", payload.remarks)
        try:
            from app.email_notifier import trigger_proposal_email
            trigger_proposal_email(str(proposal.team_id), "approved", proposal.title, remarks=payload.remarks)
        except Exception as e_err:
            print(f"Failed to trigger proposal approval email: {e_err}")
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)
    
    return ok(data={"id": proposal.id, "status": proposal.status}, message="Proposal approved")


@router.post("/reject")
async def reject_proposal(
    payload: ProposalActionRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        proposal = await ProposalService.update_status(db, payload.proposal_id, "rejected", payload.remarks)
        try:
            from app.email_notifier import trigger_proposal_email
            trigger_proposal_email(str(proposal.team_id), "rejected", proposal.title, remarks=payload.remarks)
        except Exception as e_err:
            print(f"Failed to trigger proposal rejection email: {e_err}")
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)
        
    return ok(data={"id": proposal.id, "status": proposal.status}, message="Proposal rejected")


@router.post("/revision")
async def request_revision(
    payload: ProposalActionRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        proposal = await ProposalService.update_status(db, payload.proposal_id, "revision", payload.remarks)
        try:
            from app.email_notifier import trigger_proposal_email
            trigger_proposal_email(str(proposal.team_id), "revision", proposal.title, remarks=payload.remarks)
        except Exception as e_err:
            print(f"Failed to trigger proposal revision email: {e_err}")
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)
        
    return ok(data={"id": proposal.id, "status": proposal.status}, message="Revision requested")
