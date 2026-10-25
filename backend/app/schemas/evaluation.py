import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class EvaluationResponse(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    schedule_id: uuid.UUID
    panel_id: uuid.UUID
    semester_id: uuid.UUID
    type: str
    marks: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluationCreate(BaseModel):
    team_id: uuid.UUID
    schedule_id: uuid.UUID
    panel_id: uuid.UUID
    semester_id: uuid.UUID
    type: str # proposal | mid | final
    marks: float


class EvaluationUpdate(BaseModel):
    marks: Optional[float] = None


