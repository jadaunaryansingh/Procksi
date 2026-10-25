from app.repositories.base import BaseRepository
from app.models.email_log import EmailLog
from pydantic import BaseModel
from typing import Optional

class EmailLogCreate(BaseModel):
    recipient: str
    subject: str
    body: str
    status: str
    error_message: Optional[str] = None
    admin_id: Optional[str] = None

class EmailLogUpdate(BaseModel):
    pass

class EmailLogRepository(BaseRepository[EmailLog, EmailLogCreate, EmailLogUpdate]):
    pass

email_log_repo = EmailLogRepository(EmailLog)
