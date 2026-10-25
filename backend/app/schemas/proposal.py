import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ProposalResponse(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    semester_id: uuid.UUID
    title: str
    description: Optional[str]
    document_url: Optional[str]
    ai_score: Optional[float]
    status: str
    submitted_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProposalListResponse(BaseModel):
    proposals: list[ProposalResponse]


class ProposalDetailResponse(ProposalResponse):
    team_members: list[dict] = []


class ProposalCreate(BaseModel):
    title: str
    description: Optional[str] = None
    document_url: Optional[str] = None
    team_id: uuid.UUID
    semester_id: uuid.UUID


class ProposalUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    document_url: Optional[str] = None
    ai_score: Optional[float] = None
    status: Optional[str] = None


class ProposalActionRequest(BaseModel):
    proposal_id: uuid.UUID
    remarks: Optional[str] = None
