import uuid
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.evaluation import Evaluation
from app.models.schedule import Schedule
from app.repositories.evaluation_repo import evaluation_repo
from app.repositories.schedule_repo import schedule_repo

class EvaluationService:
    @staticmethod
    async def submit_evaluation(
        db: AsyncSession, 
        schedule_id: uuid.UUID, 
        type: str, 
        marks: float
    ) -> Evaluation:
        if type not in {"proposal", "mid", "final"}:
            raise ValueError("type must be one of: proposal, mid, final")

        schedule = await schedule_repo.get(db, schedule_id)
        if not schedule:
            raise ValueError("Schedule not found")

        # Duplicate check
        dup_result = await db.execute(
            select(Evaluation).where(
                Evaluation.schedule_id == schedule_id,
                Evaluation.type == type,
            )
        )
        if dup_result.scalar_one_or_none():
            raise ValueError(f"An evaluation of type '{type}' already exists for this schedule")

        evaluation_in = {
            "team_id": schedule.team_id,
            "schedule_id": schedule.id,
            "panel_id": schedule.panel_id,
            "semester_id": schedule.semester_id,
            "type": type,
            "marks": marks,
        }
        
        return await evaluation_repo.create(db, obj_in=evaluation_in)

    @staticmethod
    async def list_evaluations(
        db: AsyncSession, 
        page: int = 1, 
        limit: int = 100, 
        semester_id: Optional[uuid.UUID] = None,
        team_id: Optional[uuid.UUID] = None
    ) -> Tuple[List[Evaluation], int]:
        filters = {}
        if semester_id:
            filters["semester_id"] = semester_id
        if team_id:
            filters["team_id"] = team_id
            
        total = await evaluation_repo.count(db, **filters)
        
        query = select(Evaluation)
        for field, value in filters.items():
            query = query.where(getattr(Evaluation, field) == value)
            
        result = await db.execute(query.offset((page - 1) * limit).limit(limit))
        return result.scalars().all(), total
