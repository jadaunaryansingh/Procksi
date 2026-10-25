import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, UUID, func, Integer, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.enums import SemesterType


class SemesterConfig(Base):
    __tablename__ = "semester_config"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    year: Mapped[str] = mapped_column(String(20), nullable=False)
    semester_type: Mapped[str] = mapped_column(SemesterType, nullable=False, default="odd")
    academic_level: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    semester_number: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    branch: Mapped[str] = mapped_column(String(50), nullable=False, default="B.Tech CS")
    team_size_min: Mapped[int] = mapped_column(nullable=False)
    team_size_max: Mapped[int] = mapped_column(nullable=False)
    number_of_presentations: Mapped[int] = mapped_column(nullable=False, default=3)
    proposal_weight: Mapped[float] = mapped_column(nullable=False)
    mid_weight: Mapped[float] = mapped_column(nullable=False)
    final_weight: Mapped[float] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_locked: Mapped[bool] = mapped_column(nullable=False, default=False)
    lock_teams: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lock_marks: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    results_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    teams: Mapped[list["Team"]] = relationship(
        "Team", back_populates="semester", lazy="select"
    )
    proposals: Mapped[list["Proposal"]] = relationship(
        "Proposal", back_populates="semester", lazy="select"
    )
    panels: Mapped[list["Panel"]] = relationship(
        "Panel", back_populates="semester", lazy="select"
    )
    schedules: Mapped[list["Schedule"]] = relationship(
        "Schedule", back_populates="semester", lazy="select"
    )
    evaluations: Mapped[list["Evaluation"]] = relationship(
        "Evaluation", back_populates="semester", lazy="select"
    )
    deadlines: Mapped[list["Deadline"]] = relationship(
        "Deadline", back_populates="semester", lazy="select"
    )
    students: Mapped[list["Student"]] = relationship(
        "Student", back_populates="semester", lazy="select"
    )

    __table_args__ = (
        UniqueConstraint("year", "semester_type", "academic_level", "branch", name="uq_semester_identity"),
    )
