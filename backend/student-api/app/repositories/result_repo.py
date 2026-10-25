from app.repositories.base import BaseRepository
from app.models.result import Result
from app.schemas.result import ResultCreate, ResultUpdate

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import uuid

class ResultRepository(BaseRepository[Result, ResultCreate, ResultUpdate]):
    async def get_by_team(self, db: AsyncSession, team_id: uuid.UUID) -> Optional[Result]:
        query = select(self.model).where(self.model.team_id == team_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

result_repo = ResultRepository(Result)
