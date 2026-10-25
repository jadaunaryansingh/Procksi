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
    section: str


class StudentPreviewResponse(BaseModel):
    valid: list[StudentUploadRow]
    duplicates: list[StudentUploadRow]
    invalid: list[dict]


class StudentCreate(BaseModel):
    student_id: str
    name: str
    email: EmailStr
    year: int
    branch: str
    section: str
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
    section: str
    status: str
    semester_id: Optional[uuid.UUID] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StudentListResponse(BaseModel):
    students: list[StudentResponse]


class StudentStatusUpdate(BaseModel):
    status: str  # active | inactive | graduated
