import uuid
from typing import List, Optional
from pydantic import BaseModel


class SendMailRequest(BaseModel):
    recipients: List[str]
    subject: Optional[str] = None
    template: str
    body: Optional[str] = None
    deadline: Optional[str] = None
    team_name: Optional[str] = None
    mentor_name: Optional[str] = None
    date: Optional[str] = None
    time_slot: Optional[str] = None
    room: Optional[str] = None
    total_score: Optional[float] = None
