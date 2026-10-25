import uuid
from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict

class AdminResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    role: str

    model_config = ConfigDict(from_attributes=True)

class AdminCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "ADMIN"

class AdminUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[str] = None
