import uuid
from datetime import datetime, date, time
from sqlalchemy import String, ForeignKey, Index, Date, Time, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.team import Team
    from app.models.panel import Panel
    from app.models.semester_config import SemesterConfig
    from app.models.evaluation import Evaluation


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    panel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("panels.id"), nullable=False)
    semester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semester_config.id"), nullable=False
    )  # denormalized for faster filtering
    room: Mapped[str] = mapped_column(String(100), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    time_slot: Mapped[str] = mapped_column(String(50), nullable=False)
    mode: Mapped[str] = mapped_column(String(50), nullable=False, default="offline")

    team: Mapped["Team"] = relationship("Team", back_populates="schedules", lazy="select")
    panel: Mapped["Panel"] = relationship("Panel", back_populates="schedules", lazy="select")
    semester: Mapped["SemesterConfig"] = relationship(
        "SemesterConfig", back_populates="schedules", lazy="select"
    )
    evaluations: Mapped[list["Evaluation"]] = relationship(
        "Evaluation", back_populates="schedule", lazy="select"
    )

    __table_args__ = (
        Index("ix_schedules_team_id", "team_id"),
        Index("ix_schedules_panel_id", "panel_id"),
        Index("ix_schedules_semester_id", "semester_id"),
        Index("ix_schedules_date_time_slot", "date", "time_slot"),
    )
