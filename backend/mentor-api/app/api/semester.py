import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_admin, get_super_admin
from app.repositories.semester_repo import semester_repo
from app.schemas.semester import SemesterConfigCreate, SemesterConfigUpdate, SemesterLockRequest, SemesterConfigResponse, SemesterActivateRequest
from app.schemas.common import ok, err, StandardResponse

router = APIRouter(prefix="/api/admin/semester", tags=["Semester"])


@router.post("/config", response_model=StandardResponse[SemesterConfigResponse])
async def create_semester_config(
    payload: SemesterConfigCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_super_admin),
):
    # Weight validation is handled by Pydantic validator in SemesterConfigCreate
    semester = await semester_repo.create(db, obj_in=payload)
    return ok(data=semester)


@router.get("/config", response_model=StandardResponse[List[SemesterConfigResponse]])
async def list_semester_configs(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    semesters = await semester_repo.get_multi(db, limit=100)
    # Most recent first
    data = sorted(semesters, key=lambda x: x.created_at, reverse=True)
    return ok(data=data)


@router.get("/active", response_model=StandardResponse[SemesterConfigResponse])
async def get_active_semester(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    semester = await semester_repo.get_active(db)
    if not semester:
        return err("NOT_FOUND", "No semester config found. Please create one.", 404)
    
    return ok(data=semester)


@router.patch("/config/{semester_id}", response_model=StandardResponse[SemesterConfigResponse])
async def update_semester_config(
    semester_id: uuid.UUID,
    payload: SemesterConfigUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_super_admin),
):
    semester = await semester_repo.get(db, semester_id)
    if not semester:
        return err("NOT_FOUND", "Semester config not found", 404)
    
    if semester.is_locked:
        return err("FORBIDDEN", "Locked semester configurations cannot be updated", 403)

    semester = await semester_repo.update(db, db_obj=semester, obj_in=payload)
    return ok(data=semester, message="Semester configuration updated")


@router.patch("/lock")
async def lock_semester(
    payload: SemesterLockRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_super_admin),
):
    semester = await semester_repo.get(db, payload.semester_id)
    if not semester:
        return err("NOT_FOUND", "Semester config not found", 404)

    semester = await semester_repo.update(db, db_obj=semester, obj_in={"is_locked": payload.is_locked})

    action = "locked" if payload.is_locked else "unlocked"
    return ok(
        data={"id": semester.id, "is_locked": semester.is_locked},
        message=f"Semester {action}",
    )


@router.patch("/activate")
async def activate_semester(
    payload: SemesterActivateRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_super_admin),
):
    """Set a specific semester as the active one (deactivates all others)."""
    try:
        semester = await semester_repo.set_active(db, payload.semester_id)
    except ValueError as e:
        return err("NOT_FOUND", str(e), 404)

    return ok(
        data={"id": semester.id, "is_active": semester.is_active},
        message=f"Semester '{semester.year} · {semester.semester_type.capitalize()} · Year {semester.academic_level}' is now active",
    )
