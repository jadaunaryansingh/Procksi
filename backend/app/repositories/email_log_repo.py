import uuid
from app.repositories.base import BaseRepository
from app.models.email_log import EmailLog
from pydantic import BaseModel
from typing import Optional

class EmailLogCreate(BaseModel):
    # Matches the EmailLog ORM columns (the old schema's fields did not exist on the model).
    subject: str
    body: str
    recipients: list[str]
    sent_by: uuid.UUID

class EmailLogUpdate(BaseModel):
    pass

class EmailLogRepository(BaseRepository[EmailLog, EmailLogCreate, EmailLogUpdate]):
    pass

email_log_repo = EmailLogRepository(EmailLog)
