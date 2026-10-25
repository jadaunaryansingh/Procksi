import uuid
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.proposal import Proposal
from app.models.team import Team
from app.models.semester_config import SemesterConfig
from app.repositories.proposal_repo import proposal_repo
from app.repositories.team_repo import team_repo
from app.repositories.semester_repo import semester_repo
from app.services.ai_service import score_proposal

class ProposalService:
    @staticmethod
    async def create_proposal(
        db: AsyncSession, 
        team_id: uuid.UUID, 
        title: str, 
        description: Optional[str] = None, 
        document_url: Optional[str] = None
    ) -> Proposal:
        team = await team_repo.get(db, team_id)
        if not team:
            raise ValueError("Team not found")

        semester = await semester_repo.get(db, team.semester_id)
        if semester and semester.is_locked:
            raise ValueError("Semester is locked; proposal submission not permitted")

        # Duplicate title check
        dup_result = await db.execute(
            select(Proposal).where(
                Proposal.title == title,
                Proposal.semester_id == team.semester_id,
            )
        )
        if dup_result.scalar_one_or_none():
            raise ValueError("A proposal with this title already exists for the current semester")

        proposal_in = {
            "team_id": team_id,
            "semester_id": team.semester_id,
            "title": title,
            "description": description,
            "document_url": document_url,
            "status": "pending"
        }
        
        # We can't use repo.create easily if we want to add ai_score before commit, 
        # or just update it after. BaseRepository handles commit.
        
        proposal = await proposal_repo.create(db, obj_in=proposal_in)

        # AI Scoring (Stub)
        ai_score = await score_proposal(
            title=proposal.title,
            description=proposal.description or "",
            document_url=proposal.document_url,
        )
        proposal = await proposal_repo.update(db, db_obj=proposal, obj_in={"ai_score": ai_score})

        return proposal

    @staticmethod
    async def list_proposals(
        db: AsyncSession, 
        page: int = 1, 
        limit: int = 100, 
        status: Optional[str] = None, 
        semester_id: Optional[uuid.UUID] = None
    ) -> Tuple[List[Proposal], int]:
        filters = {}
        if status:
            filters["status"] = status
        if semester_id:
            filters["semester_id"] = semester_id
            
        total = await proposal_repo.count(db, **filters)
        
        query = select(Proposal)
        for field, value in filters.items():
            query = query.where(getattr(Proposal, field) == value)
        
        result = await db.execute(query.offset((page - 1) * limit).limit(limit))
        return result.scalars().all(), total

    @staticmethod
    async def update_status(db: AsyncSession, proposal_id: uuid.UUID, new_status: str, remarks: Optional[str] = None) -> Proposal:
        proposal = await proposal_repo.get(db, proposal_id)
        if not proposal:
            raise ValueError("Proposal not found")

        semester = await semester_repo.get(db, proposal.semester_id)
        if semester and semester.is_locked:
            raise ValueError("Semester is locked; proposal actions are not permitted")

        update_data = {"status": new_status}
        if remarks is not None:
            update_data["remarks"] = remarks

        return await proposal_repo.update(db, db_obj=proposal, obj_in=update_data)
