import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.schedule import Schedule
from app.models.team import Team
from app.models.schedule import Schedule
from app.models.team import Team
from app.api.deps import get_db, get_current_admin
from app.repositories.schedule_repo import schedule_repo
from app.schemas.schedule import ScheduleGenerateRequest, ScheduleUpdateRequest, ScheduleResponse, ScheduleCreate
from app.schemas.common import ok, paginated, err, StandardResponse
from app.services.schedule_service import ScheduleService

router = APIRouter(prefix="/api/admin/schedule", tags=["Schedule"])


@router.post("/generate")
async def generate_schedule(
    payload: ScheduleGenerateRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        created = await ScheduleService.generate_schedules(
            db,
            semester_id=payload.semester_id,
            dates=payload.dates,
            time_slots=payload.time_slots,
            rooms=payload.rooms,
            mode=payload.mode
        )
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)

    return ok(
        data={"created": len(created)},
        message=f"{len(created)} schedules generated",
    )


@router.get("", response_model=StandardResponse[List[ScheduleResponse]])
async def list_schedules(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    semester_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    query = (
        select(Schedule)
        .options(
            selectinload(Schedule.team).selectinload(Team.mentor)
        )
        .offset((page - 1) * limit)
        .limit(limit)
    )
    if semester_id:
        query = query.where(Schedule.semester_id == semester_id)
        
    result = await db.execute(query)
    schedules = result.scalars().all()
    
    return ok(data=[ScheduleResponse.model_validate(s).model_dump() for s in schedules])


@router.patch("/update", response_model=StandardResponse[ScheduleResponse])
async def update_schedule(
    payload: ScheduleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        schedule = await ScheduleService.update_schedule(
            db,
            schedule_id=payload.schedule_id,
            room=payload.room,
            date=payload.date,
            time_slot=payload.time_slot,
            mode=payload.mode
        )
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)

    # Re-fetch with eager loading for response
    query = select(Schedule).where(Schedule.id == schedule.id).options(
        selectinload(Schedule.team).selectinload(Team.mentor)
    )
    result = await db.execute(query)
    schedule = result.scalar_one()

    return ok(data=schedule)
@router.post("", response_model=StandardResponse[ScheduleResponse])
async def create_schedule(
    payload: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        schedule = await schedule_repo.create(db, obj_in=payload)
        # Load team and mentor for response
        query = select(Schedule).where(Schedule.id == schedule.id).options(
            selectinload(Schedule.team).selectinload(Team.mentor)
        )
        result = await db.execute(query)
        schedule = result.scalar_one()
    except Exception as e:
        return err("ACTION_FAILED", str(e), 400)

    return ok(data=schedule)
