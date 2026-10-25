import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ResultResponse(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    proposal_score: float
    mid_score: float
    final_score: float
    total_score: float
    override_reason: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResultCreate(BaseModel):
    team_id: uuid.UUID
    proposal_score: float = 0.0
    mid_score: float = 0.0
    final_score: float = 0.0
    total_score: float = 0.0


class ResultUpdate(BaseModel):
    proposal_score: Optional[float] = None
    mid_score: Optional[float] = None
    final_score: Optional[float] = None
    total_score: Optional[float] = None


class ResultOverrideRequest(BaseModel):
    team_id: uuid.UUID
    proposal_score: float
    mid_score: float
    final_score: float
    total_score: float
    reason: str


class ResultExportRow(BaseModel):
    team_id: uuid.UUID
    team_name: str
    project_title: str
    proposal_score: float
    mid_score: float
    final_score: float
    total_score: float
    override_reason: Optional[str] = None
