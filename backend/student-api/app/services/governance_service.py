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
        deadlines_list = []
        try:
            from app.core.supabase_client import supabase_client
            endpoint = "deadlines"
            if semester_id:
                endpoint += f"?semester_id=eq.{semester_id}"
            sp_rows = await supabase_client._request(endpoint)
            if sp_rows and isinstance(sp_rows, list) and len(sp_rows) > 0:
                for r in sp_rows:
                    deadlines_list.append({
                        "id": str(r.get("id", "")),
                        "title": r.get("title") or r.get("name") or r.get("type"),
                        "deadline_date": r.get("due_date") or r.get("deadline_date") or "",
                        "start_date": r.get("start_date") or "",
                        "type": r.get("type") or r.get("id")
                    })
                return deadlines_list
        except Exception:
            pass

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
                "start_date": getattr(d, 'start_date', None).isoformat() if getattr(d, 'start_date', None) else None,
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
        if type not in {"proposal", "team", "evaluation", "teamFormation", "proposalUpload", "midTerm", "finalEvaluation", "problemStatementSelection", "extraActivities", "githubRepoSubmission", "github"}:
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
        from datetime import datetime, timezone, timedelta
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        deadlines = await GovernanceService.get_deadlines(db, semester_id)
        for d in deadlines:
            d_type = d.get('type')
            is_match = (
                d_type == deadline_type or 
                (deadline_type in ('teamFormation', 'team') and d_type in ('teamFormation', 'team')) or
                (deadline_type in ('proposalUpload', 'proposal') and d_type in ('proposalUpload', 'proposal')) or
                (deadline_type in ('problemStatementSelection', 'problemStatement', 'ps') and d_type in ('problemStatementSelection', 'problemStatement', 'ps')) or
                (deadline_type in ('midTerm', 'evaluation') and d_type in ('midTerm', 'evaluation')) or
                (deadline_type in ('extraActivities', 'extra') and d_type in ('extraActivities', 'extra')) or
                (deadline_type in ('githubRepoSubmission', 'github') and d_type in ('githubRepoSubmission', 'github'))
            )
            if is_match:
                try:
                    # 1. Enforce start_date opening window if configured
                    start_date_str = d.get('start_date')
                    if start_date_str:
                        for suffix in ('Z', '+00:00', '+0000'):
                            if start_date_str.endswith(suffix):
                                start_date_str = start_date_str[:-len(suffix)]
                                break
                        if '+' in start_date_str:
                            start_date_str = start_date_str.split('+')[0]
                        start_dt = datetime.fromisoformat(start_date_str).replace(tzinfo=ist_tz)
                        if datetime.now(ist_tz) < start_dt:
                            raise HTTPException(status_code=403, detail=f"The {deadline_type} action is not open yet. It will open on {start_date_str.replace('T', ' ')}.")

                    # 2. Enforce due_date closing window
                    due_date_str = d.get('deadline_date')
                    if due_date_str:
                        for suffix in ('Z', '+00:00', '+0000'):
                            if due_date_str.endswith(suffix):
                                due_date_str = due_date_str[:-len(suffix)]
                                break
                        if '+' in due_date_str:
                            due_date_str = due_date_str.split('+')[0]
                        
                        due_date = datetime.fromisoformat(due_date_str).replace(tzinfo=ist_tz)
                        now_ist = datetime.now(ist_tz)
                        # If due_date is on today's target date, extend to 23:59:59 IST so actions stay open throughout the entire day
                        if due_date.date() == now_ist.date() or (due_date.hour in (0, 5) and due_date.minute in (0, 30)):
                            due_date = due_date.replace(hour=23, minute=59, second=59)
                        
                        if now_ist > due_date:
                            raise HTTPException(status_code=403, detail=f"The {deadline_type} deadline has passed. Action not allowed.")
                except HTTPException as h_err:
                    raise h_err
                except ValueError:
                    pass
