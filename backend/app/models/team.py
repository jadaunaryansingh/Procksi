import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import String, ForeignKey, UniqueConstraint, Index, func, UUID, Enum, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.mentor import Mentor
    from app.models.semester_config import SemesterConfig
    from app.models.team_member import TeamMember
    from app.models.proposal import Proposal
    from app.models.schedule import Schedule
    from app.models.evaluation import Evaluation
    from app.models.result import Result

from app.models.enums import TeamStatus


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    domain: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=[])
    required_skills: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=[])
    mentor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mentors.id"), nullable=True
    )
    semester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semester_config.id"), nullable=False
    )
    is_validated: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_overridden: Mapped[bool] = mapped_column(default=False, nullable=False)
    status: Mapped[str] = mapped_column(TeamStatus, default="pending", nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    mentor: Mapped[Optional["Mentor"]] = relationship(
        "Mentor", back_populates="teams", lazy="select"
    )
    semester: Mapped["SemesterConfig"] = relationship(
        "SemesterConfig", back_populates="teams", lazy="select"
    )
    members: Mapped[list["TeamMember"]] = relationship(
        "TeamMember", back_populates="team", lazy="select"
    )
    proposals: Mapped[list["Proposal"]] = relationship(
        "Proposal", back_populates="team", lazy="select"
    )
    schedules: Mapped[list["Schedule"]] = relationship(
        "Schedule", back_populates="team", lazy="select"
    )
    evaluations: Mapped[list["Evaluation"]] = relationship(
        "Evaluation", back_populates="team", lazy="select"
    )
    result: Mapped[Optional["Result"]] = relationship(
        "Result", back_populates="team", lazy="select", uselist=False
    )

    __table_args__ = (
        UniqueConstraint("project_title", "semester_id", name="uq_team_project_semester"),
        Index("ix_teams_semester_id", "semester_id"),
        Index("ix_teams_mentor_id", "mentor_id"),
    )
