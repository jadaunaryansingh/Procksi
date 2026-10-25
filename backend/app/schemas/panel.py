import uuid
from pydantic import BaseModel, ConfigDict
from typing import Optional

class PanelResponse(BaseModel):
    id: uuid.UUID
    name: str
    semester_id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)

class PanelCreate(BaseModel):
    name: str
    semester_id: uuid.UUID

class PanelUpdate(BaseModel):
    name: Optional[str] = None

class PanelMentorResponse(BaseModel):
    id: uuid.UUID
    panel_id: uuid.UUID
    mentor_id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)

class PanelMentorCreate(BaseModel):
    panel_id: uuid.UUID
    mentor_id: uuid.UUID

class PanelMentorUpdate(BaseModel):
    pass
