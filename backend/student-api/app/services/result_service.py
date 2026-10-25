import uuid
from typing import List, Optional, Tuple, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.result import Result
from app.models.team import Team
from app.models.semester_config import SemesterConfig
from app.models.evaluation import Evaluation
from app.repositories.result_repo import result_repo
from app.repositories.team_repo import team_repo
from app.repositories.semester_repo import semester_repo
from app.repositories.audit_log_repo import audit_log_repo

class ResultService:
    @staticmethod
    async def calculate_results(db: AsyncSession, semester_id: uuid.UUID) -> int:
        semester = await semester_repo.get(db, semester_id)
        if not semester:
            raise ValueError("Semester not found")

        # Optimization: Fetch teams with their evaluations in a single pass
        query = (
            select(Team)
            .where(Team.semester_id == semester_id)
            .options(selectinload(Team.evaluations))
        )
        result = await db.execute(query)
        teams = result.scalars().all()

        processed = 0
        for team in teams:
            evals = team.evaluations

            proposal_marks = [e.marks for e in evals if e.type == "proposal"]
            mid_marks = [e.marks for e in evals if e.type == "mid"]
            final_marks = [e.marks for e in evals if e.type == "final"]

            proposal_score = (sum(proposal_marks) / len(proposal_marks)) if proposal_marks else 0.0
            mid_score = (sum(mid_marks) / len(mid_marks)) if mid_marks else 0.0
            final_score = (sum(final_marks) / len(final_marks)) if final_marks else 0.0

            total_score = (
                proposal_score * (semester.proposal_weight / 100)
                + mid_score * (semester.mid_weight / 100)
                + final_score * (semester.final_weight / 100)
            )

            # Optimization: Use repository to get result by team_id
            result_row = await result_repo.get_by_team(db, team.id)

            update_data = {
                "proposal_score": proposal_score,
                "mid_score": mid_score,
                "final_score": final_score,
                "total_score": total_score,
                "override_reason": None # Reset override on recalc
            }

            if result_row:
                await result_repo.update(db, db_obj=result_row, obj_in=update_data)
            else:
                update_data["team_id"] = team.id
                await result_repo.create(db, obj_in=update_data)

            processed += 1
        return processed

    @staticmethod
    async def get_all_results(db: AsyncSession, semester_id: uuid.UUID) -> List[dict]:
        # Batch fetch teams with their results to avoid overhead
        query = (
            select(Team)
            .where(Team.semester_id == semester_id)
            .options(selectinload(Team.result))
        )
        result = await db.execute(query)
        teams = result.scalars().all()

        rows = []
        for team in teams:
            res = team.result
            rows.append({
                "id": str(res.id) if res else str(uuid.uuid4()), # temporary ID for frontend keys if no result
                "team_id": str(team.id),
                "team": {
                    "team_name": team.name,
                    "project_title": team.project_title
                },
                "proposal_score": res.proposal_score if res else 0.0,
                "mid_score": res.mid_score if res else 0.0,
                "final_score": res.final_score if res else 0.0,
                "total_score": res.total_score if res else 0.0,
                "override_reason": res.override_reason if res else None
            })
        return rows

    @staticmethod
    async def get_results_for_export(db: AsyncSession, semester_id: uuid.UUID) -> List[dict]:
        # Optimization: Batch fetch teams with their results
        query = (
            select(Team)
            .where(Team.semester_id == semester_id)
            .options(selectinload(Team.result))
        )
        result = await db.execute(query)
        teams = result.scalars().all()

        rows = []
        for team in teams:
            res = team.result
            rows.append({
                "team_id": str(team.id),
                "team_name": team.name,
                "project_title": team.project_title,
                "proposal_score": res.proposal_score if res else 0.0,
                "mid_score": res.mid_score if res else 0.0,
                "final_score": res.final_score if res else 0.0,
                "total_score": res.total_score if res else 0.0,
                "override_reason": res.override_reason if res else None
            })
        return rows
    async def override_result(
        db: AsyncSession,
        team_id: uuid.UUID,
        proposal_score: float,
        mid_score: float,
        final_score: float,
        total_score: float,
        admin_id: str,
        reason: str
    ) -> Result:
        result_res = await db.execute(
            select(Result).where(Result.team_id == team_id)
        )
        result_row = result_res.scalar_one_or_none()

        if not result_row:
            team = await team_repo.get(db, team_id)
            if not team:
                raise ValueError("Team not found")
            raise ValueError("No result record found for this team. Run /calculate first.")

        update_data = {
            "proposal_score": proposal_score,
            "mid_score": mid_score,
            "final_score": final_score,
            "total_score": total_score,
            "override_reason": reason
        }
        
        result_row = await result_repo.update(db, db_obj=result_row, obj_in=update_data)

        # Audit log
        await audit_log_repo.create(db, obj_in={
            "admin_id": admin_id,
            "action": f"result_override: {reason}",
            "entity_type": "result",
            "entity_id": str(result_row.id)
        })

        return result_row
