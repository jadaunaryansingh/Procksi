from app.repositories.base import BaseRepository
from app.models.audit_log import AuditLog
from pydantic import BaseModel

# Simple schemas for AuditLog creation if not fully defined in governance.py
class AuditLogCreate(BaseModel):
    admin_id: str
    action: str
    entity_type: str
    entity_id: str

class AuditLogUpdate(BaseModel):
    pass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

class AuditLogRepository(BaseRepository[AuditLog, AuditLogCreate, AuditLogUpdate]):
    async def get_recent_logs(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> List[AuditLog]:
        query = select(self.model).order_by(self.model.timestamp.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        return result.scalars().all()

    async def get_logs_by_entity_types(
        self,
        db: AsyncSession,
        entity_types: List[str],
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[List[AuditLog], int]:
        """Return audit logs filtered by entity_type(s), newest first, with total count."""
        from sqlalchemy import func

        base_filter = self.model.entity_type.in_(entity_types)

        # Total count
        count_q = select(func.count()).select_from(self.model).where(base_filter)
        total = (await db.execute(count_q)).scalar() or 0

        # Data
        data_q = (
            select(self.model)
            .where(base_filter)
            .order_by(self.model.timestamp.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(data_q)
        return list(result.scalars().all()), total

audit_log_repo = AuditLogRepository(AuditLog)
