import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_admin
from app.schemas.evaluation import EvaluationCreate, EvaluationResponse
from app.schemas.common import ok, paginated, err, StandardResponse
from app.services.evaluation_service import EvaluationService

router = APIRouter(prefix="/api/admin/evaluations", tags=["Evaluations"])


@router.post("", response_model=StandardResponse[EvaluationResponse])
async def submit_evaluation(
    payload: EvaluationCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        evaluation = await EvaluationService.submit_evaluation(
            db, 
            schedule_id=payload.schedule_id,
            type=payload.type,
            marks=payload.marks
        )
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)

    return ok(data=evaluation)


@router.get("")
async def list_evaluations(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    semester_id: Optional[uuid.UUID] = None,
    team_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    if not semester_id:
        from app.repositories.semester_repo import semester_repo
        active_sem = await semester_repo.get_active(db)
        if active_sem:
            semester_id = active_sem.id
    evaluations, total = await EvaluationService.list_evaluations(
        db, page, limit, semester_id, team_id
    )

    return ok(data=[
        {
            "id": e.id,
            "team_id": e.team_id,
            "schedule_id": e.schedule_id,
            "panel_id": e.panel_id,
            "semester_id": e.semester_id,
            "type": e.type,
            "marks": e.marks,
            "created_at": e.created_at.isoformat(),
        }
        for e in evaluations
    ])
