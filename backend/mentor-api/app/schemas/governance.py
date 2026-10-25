import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class DeadlineSetRequest(BaseModel):
    semester_id: uuid.UUID
    type: str  # proposal | team | evaluation
    due_date: datetime


class DeadlineCreate(BaseModel):
    semester_id: uuid.UUID
    type: str
    due_date: datetime


class DeadlineUpdate(BaseModel):
    due_date: Optional[datetime] = None


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    admin_id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class DataFreezeRequest(BaseModel):
    semester_id: uuid.UUID
    freeze: bool
