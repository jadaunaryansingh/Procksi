import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, ForeignKey, func, Integer, DateTime, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class Milestone(Base):
    __tablename__ = "milestones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[int] = mapped_column(Integer, nullable=False)  # Temporarily removed foreign key constraint
    semester_id: Mapped[str] = mapped_column(String(255), ForeignKey("semester_config.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="not_started")  # not_started | in_progress | submitted | approved
    github_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)
