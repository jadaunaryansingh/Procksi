import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_admin
from app.schemas.team import TeamValidateRequest, TeamOverrideRequest
from app.schemas.common import ok, paginated, err
from app.services.team_service import TeamService

router = APIRouter(prefix="/api/admin/teams", tags=["Teams"])


@router.get("/stats")
async def team_stats(
    semester_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    if not semester_id:
        from app.repositories.semester_repo import semester_repo
        active_sem = await semester_repo.get_active(db)
        if active_sem:
            semester_id = active_sem.id

    stats = await TeamService.get_team_stats(db, semester_id=semester_id)
    return ok(data=stats)


@router.get("/filters")
async def get_filter_options(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Return distinct branches, mentors, domains, and statuses for filter dropdowns."""
    filters = await TeamService.get_filter_options(db)
    return ok(data=filters)


@router.get("")
async def list_teams(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    branch: Optional[str] = Query(None),
    mentor_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    semester_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    if not semester_id:
        from app.repositories.semester_repo import semester_repo
        active_sem = await semester_repo.get_active(db)
        if active_sem:
            semester_id = active_sem.id
    data, total = await TeamService.list_teams_with_members(
        db, page, limit,
        branch=branch,
        mentor_id=mentor_id,
        status=status,
        search=search,
        semester_id=semester_id,
    )
    return paginated(data=data, page=page, limit=limit, total=total)


@router.post("/validate")
async def validate_team(
    payload: TeamValidateRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        team = await TeamService.validate_team(db, payload.team_id)
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)

    return ok(data={"team_id": team.id, "is_validated": True}, message="Team validated")


@router.post("/validate-all")
async def validate_all_teams(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        count = await TeamService.validate_all_teams(db)
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)

    return ok(data={"validated_count": count}, message=f"Batch validation complete. Synced {count} teams.")


@router.patch("/manual-override")
async def manual_override_team(
    payload: TeamOverrideRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        team = await TeamService.manual_override(
            db, payload.team_id, str(admin.id), payload.reason
        )
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)

    return ok(
        data={"team_id": team.id, "is_overridden": True},
        message="Team manually overridden and audit log recorded",
    )

@router.get("/unassigned")
async def get_unassigned_students(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    students = await TeamService.get_unassigned_students(db)
    return ok(data=[{
        "id": str(s.id),
        "name": s.name,
        "roll": s.student_id,
        "branch": s.branch
    } for s in students])

@router.post("/bulk-assign")
async def bulk_assign_students(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        count = await TeamService.bulk_assign_students(db, str(admin.id))
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)
    
    return ok(data={"count": count}, message=f"Successfully formed {count} teams from unassigned students.")

class ForceAssignRequest(BaseModel):
    student_id: str
    team_id: Optional[str] = None

@router.get("/conflicts")
async def get_project_conflicts(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    conflicts = await TeamService.get_project_conflicts(db)
    return ok(data=conflicts)

@router.get("/unallocated")
async def get_detailed_unallocated(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    data = await TeamService.get_detailed_unassigned(db)
    return ok(data=data)

class ResolveConflictRequest(BaseModel):
    conflict_id: str
    reason: str

@router.post("/resolve-conflict")
async def resolve_conflict(
    payload: ResolveConflictRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    import uuid
    # For now, we just log this manual override in the audit ledger
    from app.repositories.audit_log_repo import audit_log_repo
    await audit_log_repo.create(db, obj_in={
        "admin_id": str(admin.id),
        "action": f"Manual Resolve Project Conflict ({payload.conflict_id}): {payload.reason}",
        "entity_type": "project_allocation",
        "entity_id": uuid.uuid4()
    })
    await db.commit()
    return ok(message="Conflict resolved and logged successfully")

@router.post("/force-assign")
async def force_assign(
    payload: ForceAssignRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    import uuid
    try:
        t_id = uuid.UUID(payload.team_id) if payload.team_id else None
        await TeamService.force_assign_student(db, uuid.UUID(payload.student_id), t_id)
    except Exception as e:
        return err("ACTION_FAILED", str(e), 400)
    
    return ok(message="Force assignment successful")


class CreateCustomTeamRequest(BaseModel):
    leader_id: str
    member_ids: list[str]

@router.post("/create-custom")
async def create_custom_team(
    payload: CreateCustomTeamRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    import uuid
    try:
        team = await TeamService.create_custom_team(
            db, 
            uuid.UUID(payload.leader_id), 
            [uuid.UUID(m_id) for m_id in payload.member_ids]
        )
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)
    except Exception as e:
        return err("ACTION_FAILED", str(e), 400)
    
    return ok(data={"team_id": str(team.id)}, message="Custom team created successfully")

@router.get("/allocation-logs")
async def get_allocation_audit_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    logs, total = await TeamService.get_allocation_audit_logs(db, page, limit)
    return paginated(data=logs, page=page, limit=limit, total=total)

@router.get("/allocation-summary")
async def get_allocation_summary(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    summary = await TeamService.get_allocation_summary(db)
    return ok(data=summary)

class AssignToTeamRequest(BaseModel):
    student_id: str
    team_id: str

@router.post("/assign-to-team")
async def assign_student_to_team(
    payload: AssignToTeamRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Assign a specific unassigned student to a specific team (if team not full)."""
    import uuid
    try:
        result = await TeamService.force_assign_to_team(
            db, uuid.UUID(payload.student_id), uuid.UUID(payload.team_id)
        )
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)
    except Exception as e:
        return err("ACTION_FAILED", str(e), 400)
    
    return ok(data=result, message="Student assigned to team successfully")
