import uuid
from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ScheduleGenerateRequest(BaseModel):
    semester_id: uuid.UUID
    rooms: list[str]
    dates: list[str]
    time_slots: list[str]
    mode: str = "offline"


class TeamBrief(BaseModel):
    id: uuid.UUID
    name: str
    mentor: Optional["MentorBrief"] = None
    model_config = ConfigDict(from_attributes=True)


class MentorBrief(BaseModel):
    id: uuid.UUID
    name: str
    model_config = ConfigDict(from_attributes=True)


class ScheduleResponse(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    panel_id: uuid.UUID
    semester_id: uuid.UUID
    room: str
    date: date
    time_slot: str
    mode: str
    team: Optional[TeamBrief] = None

    model_config = ConfigDict(from_attributes=True)


class ScheduleUpdateRequest(BaseModel):
    schedule_id: uuid.UUID
    room: Optional[str] = None
    date: Optional[str] = None
    time_slot: Optional[str] = None
    mode: Optional[str] = None


class ScheduleCreate(BaseModel):
    team_id: uuid.UUID
    panel_id: uuid.UUID
    semester_id: uuid.UUID
    room: str
    date: date
    time_slot: str
    mode: str = "offline"


class ScheduleUpdate(BaseModel):
    room: Optional[str] = None
    date: Optional[date] = None
    time_slot: Optional[str] = None
    mode: Optional[str] = None
