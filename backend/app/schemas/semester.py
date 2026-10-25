from datetime import datetime
import uuid
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator


class SemesterConfigCreate(BaseModel):
    year: str
    semester_type: str = "odd"
    academic_level: int = 4
    semester_number: int = 7
    branch: str = "B.Tech CS"
    team_size_min: int
    team_size_max: int
    number_of_presentations: int = 3
    proposal_weight: float
    mid_weight: float
    final_weight: float

    @field_validator("semester_type")
    @classmethod
    def validate_semester_type(cls, v):
        if v not in ("odd", "even"):
            raise ValueError("semester_type must be 'odd' or 'even'")
        return v

    @field_validator("academic_level")
    @classmethod
    def validate_academic_level(cls, v):
        if v not in (1, 2, 3, 4):
            raise ValueError("academic_level must be 1, 2, 3, or 4")
        return v

    @field_validator("final_weight")
    @classmethod
    def weights_must_sum_to_100(cls, v, info):
        data = info.data
        total = data.get("proposal_weight", 0) + data.get("mid_weight", 0) + v
        if abs(total - 100.0) > 0.01:
            raise ValueError("proposal_weight + mid_weight + final_weight must equal 100")
        return v


class SemesterConfigUpdate(BaseModel):
    year: Optional[str] = None
    semester_type: Optional[str] = None
    academic_level: Optional[int] = None
    semester_number: Optional[int] = None
    branch: Optional[str] = None
    team_size_min: Optional[int] = None
    team_size_max: Optional[int] = None
    number_of_presentations: Optional[int] = None
    proposal_weight: Optional[float] = None
    mid_weight: Optional[float] = None
    final_weight: Optional[float] = None
    is_active: Optional[bool] = None
    is_locked: Optional[bool] = None
    lock_teams: Optional[bool] = None
    lock_marks: Optional[bool] = None
    results_published: Optional[bool] = None


class SemesterConfigResponse(BaseModel):
    id: uuid.UUID
    year: str
    semester_type: str
    academic_level: int
    semester_number: int
    branch: str
    team_size_min: int
    team_size_max: int
    number_of_presentations: int
    proposal_weight: float
    mid_weight: float
    final_weight: float
    is_active: bool
    is_locked: bool
    lock_teams: bool
    lock_marks: bool
    results_published: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SemesterLockRequest(BaseModel):
    semester_id: uuid.UUID
    is_locked: bool


class SemesterActivateRequest(BaseModel):
    semester_id: uuid.UUID
