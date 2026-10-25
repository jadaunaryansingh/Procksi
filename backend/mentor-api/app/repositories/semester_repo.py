from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.base import BaseRepository
from app.models.semester_config import SemesterConfig
from app.schemas.semester import SemesterConfigCreate, SemesterConfigUpdate

class SemesterConfigRepository(BaseRepository[SemesterConfig, SemesterConfigCreate, SemesterConfigUpdate]):
    async def get_active(self, db: AsyncSession) -> Optional[SemesterConfig]:
        """
        Returns the semester configuration explicitly marked as active.
        Falls back to the most recent if none is marked active.
        """
        # First try: explicit is_active flag
        query = select(self.model).where(self.model.is_active == True).limit(1)
        result = await db.execute(query)
        semester = result.scalar_one_or_none()
        if semester:
            return semester

        # Fallback: most recent by created_at
        query = select(self.model).order_by(self.model.created_at.desc()).limit(1)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_active_multi(self, db: AsyncSession) -> list[SemesterConfig]:
        """
        Returns all semester configurations explicitly marked as active.
        Falls back to the most recent if none is marked active.
        """
        # First try: explicit is_active flag
        query = select(self.model).where(self.model.is_active == True)
        result = await db.execute(query)
        semesters = list(result.scalars().all())
        if semesters:
            return semesters

        # Fallback: most recent by created_at
        query = select(self.model).order_by(self.model.created_at.desc()).limit(1)
        result = await db.execute(query)
        fallback = result.scalar_one_or_none()
        return [fallback] if fallback else []

    async def set_active(self, db: AsyncSession, semester_id) -> SemesterConfig:
        """
        Set a semester as active and deactivate all others.
        """
        # Deactivate all
        await db.execute(
            update(self.model).values(is_active=False)
        )
        # Activate the target
        semester = await self.get(db, semester_id)
        if not semester:
            raise ValueError("Semester config not found")
        semester.is_active = True
        await db.commit()
        await db.refresh(semester)
        return semester


semester_repo = SemesterConfigRepository(SemesterConfig)
