import uuid
from datetime import datetime
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, distinct

from app.models.deadline import Deadline
from app.models.semester_config import SemesterConfig
from app.models.audit_log import AuditLog
from app.models.student import Student
from app.models.team import Team
from app.models.proposal import Proposal
from app.models.mentor import Mentor
from app.repositories.deadline_repo import deadline_repo
from app.repositories.semester_repo import semester_repo
from app.repositories.audit_log_repo import audit_log_repo

class GovernanceService:
    @staticmethod
    async def get_system_status(db: AsyncSession) -> dict:
        # Merge all aggregations AND the active semester lookup into a single database round-trip
        # This completely eliminates N+1 sequence delays for a remote DB.
        # teams_validation is the canonical team table; public.teams is the legacy
        # int table full of invalid placeholder rows. Count from teams_validation.
        # Several batches (B.Tech years) can be active at once -> join their years.
        query = select(
            select(func.string_agg(distinct(SemesterConfig.year), ', ')).where(SemesterConfig.is_active == True).scalar_subquery().label("active_semester_year"),
            select(func.count(Student.id)).scalar_subquery().label("total_students"),
            select(func.count()).select_from(text("teams_validation")).scalar_subquery().label("total_teams"),
            select(func.count(Proposal.id)).where(Proposal.status == 'pending').scalar_subquery().label("pending_proposals"),
            select(func.count(Mentor.id)).scalar_subquery().label("total_mentors"),
            select(func.count()).select_from(text("teams_validation")).where(text('''"validationStatus" = \'Valid\'''')).scalar_subquery().label("validated_teams"),
        )
        stats_result = await db.execute(query)
        stats_row = stats_result.one()

        total_st = stats_row.total_students or 0
        total_tm = stats_row.total_teams or 0
        pending_prop = stats_row.pending_proposals or 0
        total_ment = stats_row.total_mentors or 0
        val_teams = stats_row.validated_teams or 0
        
        return {
            "total_students": total_st,
            "total_teams": total_tm,
            "pending_proposals": pending_prop,
            "total_mentors": total_ment,
            "validated_teams": val_teams,
            "db_connected": True,
            "active_semester": stats_row.active_semester_year or "None",
            "active_deadlines": [], # Fetched independently via frontend /deadlines endpoint
            "semester_progress": int((val_teams / total_tm) * 100) if total_tm > 0 else 0
        }

    @staticmethod
    async def get_deadlines(db: AsyncSession, semester_id: Optional[uuid.UUID] = None) -> List[dict]:
        if not semester_id:
            # Subquery to resolve latest semester in a single round-trip
            recent_semester_id_subq = select(SemesterConfig.id).order_by(SemesterConfig.created_at.desc()).limit(1).scalar_subquery()
            res = await db.execute(select(Deadline).where(Deadline.semester_id == recent_semester_id_subq))
        else:
            res = await db.execute(select(Deadline).where(Deadline.semester_id == semester_id))
            
        deadlines = res.scalars().all()
        return [
            {
                "id": str(d.id),
                "title": f"{d.type.capitalize()} Submission",
                "deadline_date": d.due_date.isoformat(),
                "type": d.type
            }
            for d in deadlines
        ]
    @staticmethod
    async def set_deadline(
        db: AsyncSession, 
        semester_id: uuid.UUID, 
        type: str, 
        due_date: datetime
    ) -> Deadline:
        if type not in {"proposal", "team", "evaluation", "teamFormation", "proposalUpload", "midTerm", "finalEvaluation"}:
            raise ValueError(f"Invalid deadline type: {type}")

        semester = await semester_repo.get(db, semester_id)
        if not semester:
            raise ValueError("Semester not found")

        # Upsert
        existing_result = await db.execute(
            select(Deadline).where(
                Deadline.semester_id == semester_id,
                Deadline.type == type,
            )
        )
        deadline = existing_result.scalar_one_or_none()

        if deadline:
            return await deadline_repo.update(db, db_obj=deadline, obj_in={"due_date": due_date})
        else:
            return await deadline_repo.create(db, obj_in={
                "semester_id": semester_id,
                "type": type,
                "due_date": due_date
            })

    @staticmethod
    async def freeze_data(
        db: AsyncSession, 
        semester_id: uuid.UUID, 
        freeze: bool, 
        admin_id: str
    ) -> SemesterConfig:
        semester = await semester_repo.get(db, semester_id)
        if not semester:
            raise ValueError("Semester not found")

        semester = await semester_repo.update(db, db_obj=semester, obj_in={"is_locked": freeze})

        # Audit log
        await audit_log_repo.create(db, obj_in={
            "admin_id": admin_id,
            "action": "data_freeze" if freeze else "data_unfreeze",
            "entity_type": "semester_config",
            "entity_id": str(semester.id)
        })

        return semester

    @staticmethod
    async def get_audit_logs(
        db: AsyncSession, 
        page: int = 1, 
        limit: int = 100,
        skip_count: bool = False
    ) -> Tuple[List[AuditLog], int]:
        total = 0
        # For the dashboard which only asks for `limit=4`, skipping COUNT(*) cuts latency in half
        if not skip_count:
            total = await audit_log_repo.count(db)
            
        logs = await audit_log_repo.get_recent_logs(
            db, 
            skip=(page - 1) * limit, 
            limit=limit
        )
        return logs, total

    @staticmethod
    async def enforce_deadline(db: AsyncSession, semester_id: Optional[uuid.UUID], deadline_type: str) -> None:
        from fastapi import HTTPException
        from datetime import datetime, timezone
        deadlines = await GovernanceService.get_deadlines(db, semester_id)
        for d in deadlines:
            if d['type'] == deadline_type:
                try:
                    due_date_str = d['deadline_date']
                    if due_date_str.endswith('Z'):
                        due_date_str = due_date_str[:-1] + '+00:00'
                    due_date = datetime.fromisoformat(due_date_str)
                    if due_date.tzinfo is None:
                        due_date = due_date.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) > due_date:
                        raise HTTPException(status_code=403, detail=f"The {deadline_type} deadline has passed. Action not allowed.")
                except ValueError:
                    pass

