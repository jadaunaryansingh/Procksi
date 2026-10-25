import uuid
from typing import Optional
from pydantic import BaseModel, ConfigDict


class MentorResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    expertise: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class MentorCreate(BaseModel):
    name: str
    email: str
    expertise: Optional[str] = None


class MentorUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    expertise: Optional[str] = None


class MentorAssignRequest(BaseModel):
    team_id: uuid.UUID
    mentor_id: uuid.UUID


class MentorChangeRequest(BaseModel):
    team_id: uuid.UUID
    new_mentor_id: uuid.UUID
