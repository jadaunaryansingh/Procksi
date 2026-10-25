import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class TeamMemberResponse(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    role: str
    model_config = ConfigDict(from_attributes=True)


class TeamMemberCreate(BaseModel):
    team_id: uuid.UUID
    student_id: uuid.UUID
    role: str = "MEMBER"


class TeamMemberUpdate(BaseModel):
    role: Optional[str] = None


class TeamResponse(BaseModel):
    id: uuid.UUID
    name: str
    project_title: str
    mentor_id: Optional[uuid.UUID]
    semester_id: uuid.UUID
    is_validated: bool
    is_overridden: bool
    created_at: datetime
    members: list[TeamMemberResponse] = []

    model_config = ConfigDict(from_attributes=True)


class TeamCreate(BaseModel):
    name: str
    project_title: str
    semester_id: uuid.UUID
    mentor_id: Optional[uuid.UUID] = None


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    project_title: Optional[str] = None
    mentor_id: Optional[uuid.UUID] = None
    is_validated: Optional[bool] = None
    is_overridden: Optional[bool] = None


class TeamValidateRequest(BaseModel):
    team_id: uuid.UUID


class TeamOverrideRequest(BaseModel):
    team_id: uuid.UUID
    reason: str
