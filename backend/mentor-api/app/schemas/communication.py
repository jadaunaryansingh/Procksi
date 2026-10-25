import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
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


class SendCommunicationRequest(BaseModel):
    """Drive the Communication Agent: pick an audience segment + a template (or a
    custom subject/body), supply a context for placeholder rendering, and send."""
    segment: Optional[str] = None
    template_code: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    context: Dict[str, Any] = {}
    team_id: Optional[uuid.UUID] = None
    semester_id: Optional[uuid.UUID] = None


class ScheduleCommunicationRequest(BaseModel):
    """Queue a single communication to fire automatically at ``send_at``."""
    send_at: datetime
    segment: Optional[str] = None
    template_code: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    context: Dict[str, Any] = {}
    team_id: Optional[uuid.UUID] = None
    semester_id: Optional[uuid.UUID] = None


class SequenceStep(BaseModel):
    template_code: Optional[str] = None
    segment: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    context: Dict[str, Any] = {}
    offset_days: float = 0  # days after `base` to fire this step


class ScheduleSequenceRequest(BaseModel):
    """Queue a sequence of triggers (e.g. kickoff now, team-formation in 3 days)."""
    steps: List[SequenceStep]
    base: Optional[datetime] = None       # defaults to "now" on the server
    semester_id: Optional[uuid.UUID] = None
