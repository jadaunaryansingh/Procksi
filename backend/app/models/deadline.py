import uuid
from datetime import datetime
from sqlalchemy import ForeignKey, Index, UUID, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Deadline(Base):
    __tablename__ = "deadlines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    semester_id: Mapped[str] = mapped_column(
        String, ForeignKey("semester_config.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    start_date: Mapped[str | None] = mapped_column(String, nullable=True)
    due_date: Mapped[datetime] = mapped_column(nullable=False)

    semester: Mapped["SemesterConfig"] = relationship(
        "SemesterConfig", back_populates="deadlines", lazy="select"
    )

    __table_args__ = (Index("ix_deadlines_semester_type", "semester_id", "type"),)
