import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict


class StudentUploadRow(BaseModel):
    student_id: str
    name: str
    email: EmailStr
    year: int
    branch: str
    section: Optional[str] = None


class RosterCandidate(BaseModel):
    """The best-matching existing roster row for a flagged upload row."""
    student_id: str
    name: str
    email: str


class ReviewRow(BaseModel):
    """An uncertain upload row routed to the human-review queue."""
    row: dict
    score: float
    reason: str
    match_type: str  # "name" | "id_near"
    phonetic_match: bool = False
    strong: bool = False
    candidate: Optional[RosterCandidate] = None


class InvalidRow(BaseModel):
    row: dict
    reason: str


class StudentPreviewResponse(BaseModel):
    # `valid` / `duplicates` stay raw rows and `invalid` stays {row, reason} to
    # preserve the existing /preview contract; `review` and `summary` are additive.
    valid: list[dict]
    duplicates: list[dict]
    invalid: list[InvalidRow]
    review: list[ReviewRow] = []
    summary: Optional[dict] = None


class SaveSelectedRequest(BaseModel):
    """Persist exactly the rows the admin approved (clean rows + accepted review rows)."""
    semester_id: uuid.UUID
    rows: list[dict]


class StudentCreate(BaseModel):
    student_id: str
    name: str
    email: EmailStr
    year: int
    branch: str
    section: Optional[str] = None
    status: str = "active"
    semester_id: Optional[uuid.UUID] = None

class StudentUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    year: Optional[int] = None
    branch: Optional[str] = None
    section: Optional[str] = None
    status: Optional[str] = None

class StudentResponse(BaseModel):
    id: uuid.UUID
    student_id: str
    name: str
    email: str
    year: int
    branch: str
    section: Optional[str] = None
    status: str
    semester_id: Optional[uuid.UUID] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StudentListResponse(BaseModel):
    students: list[StudentResponse]


class StudentStatusUpdate(BaseModel):
    status: str  # active | inactive | graduated
