import uuid
from datetime import datetime
from sqlalchemy import String, Text, ForeignKey, func, UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    recipients: Mapped[list] = mapped_column(JSONB, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)
    sent_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("admins.id"), nullable=False)

    sender: Mapped["Admin"] = relationship(
        "Admin", back_populates="email_logs", lazy="select"
    )
