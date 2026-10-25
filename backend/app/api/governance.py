import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_super_admin, get_current_admin
from app.schemas.governance import DeadlineSetRequest, DataFreezeRequest
from app.schemas.common import ok, paginated, err
from app.services.governance_service import GovernanceService

router = APIRouter(prefix="/api/admin/governance", tags=["Governance"])


@router.get("/status")
async def get_system_status(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    status = await GovernanceService.get_system_status(db)
    return ok(data=status)


@router.get("/deadlines")
async def get_deadlines(
    semester_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    deadlines = await GovernanceService.get_deadlines(db, semester_id)
    return ok(data=deadlines)


@router.post("/deadline/set")
async def set_deadline(
    payload: DeadlineSetRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_super_admin),
):
    try:
        deadline = await GovernanceService.set_deadline(
            db, payload.semester_id, payload.type, payload.due_date
        )
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)

    return ok(
        data={
            "id": deadline.id,
            "semester_id": deadline.semester_id,
            "type": deadline.type,
            "due_date": deadline.due_date.isoformat(),
        },
        message="Deadline set",
    )


@router.patch("/data/freeze")
async def freeze_data(
    payload: DataFreezeRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_super_admin),
):
    try:
        semester = await GovernanceService.freeze_data(
            db, payload.semester_id, payload.freeze, str(admin.id)
        )
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)

    action = "frozen" if payload.freeze else "unfrozen"
    return ok(
        data={"semester_id": semester.id, "is_locked": semester.is_locked},
        message=f"Data {action} for semester {semester.id}",
    )


@router.get("/audit/logs")
async def get_audit_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_super_admin),
):
    # Optimization for dashboard widget which only fetches latest ~4 items footprint
    skip_count = limit <= 10
    logs, total = await GovernanceService.get_audit_logs(db, page, limit, skip_count=skip_count)

    return paginated(
        data=[
            {
                "id": log.id,
                "admin_id": log.admin_id,
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "timestamp": log.timestamp.isoformat(),
            }
            for log in logs
        ],
        page=page,
        limit=limit,
        total=total,
    )
