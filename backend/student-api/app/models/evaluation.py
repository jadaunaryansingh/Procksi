import uuid
from datetime import datetime
from sqlalchemy import ForeignKey, UniqueConstraint, Index, func, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING
from app.core.database import Base
from app.models.enums import EvaluationType

if TYPE_CHECKING:
    from app.models.team import Team
    from app.models.schedule import Schedule
    from app.models.panel import Panel
    from app.models.semester_config import SemesterConfig

# team_id, panel_id, semester_id are denormalized for query performance
# and must stay consistent with schedule_id.


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    schedule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("schedules.id"), nullable=False)
    panel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("panels.id"), nullable=False)
    semester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semester_config.id"), nullable=False
    )  # denormalized
    type: Mapped[str] = mapped_column(EvaluationType, nullable=False)
    marks: Mapped[float] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    team: Mapped["Team"] = relationship("Team", back_populates="evaluations", lazy="select")
    schedule: Mapped["Schedule"] = relationship(
        "Schedule", back_populates="evaluations", lazy="select"
    )
    panel: Mapped["Panel"] = relationship("Panel", back_populates="evaluations", lazy="select")
    semester: Mapped["SemesterConfig"] = relationship(
        "SemesterConfig", back_populates="evaluations", lazy="select"
    )

    __table_args__ = (
        # Prevents duplicate evaluation type for the same scheduled session
        UniqueConstraint("schedule_id", "type", name="uq_evaluation_schedule_type"),
        Index("ix_evaluations_team_id", "team_id"),
        Index("ix_evaluations_schedule_id", "schedule_id"),
        Index("ix_evaluations_semester_id", "semester_id"),
    )
