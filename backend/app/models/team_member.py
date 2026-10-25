import uuid
from sqlalchemy import ForeignKey, UniqueConstraint, Index, text, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.enums import TeamRole


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    role: Mapped[str] = mapped_column(TeamRole, nullable=False, default="MEMBER")

    team: Mapped["Team"] = relationship("Team", back_populates="members", lazy="select")
    student: Mapped["Student"] = relationship(
        "Student", back_populates="team_membership", lazy="select"
    )

    __table_args__ = (
        # One student per team globally
        UniqueConstraint("student_id", name="uq_team_member_student"),
        # One leader per team via partial unique index
        Index(
            "uq_team_leader",
            "team_id",
            unique=True,
            postgresql_where=text("role = 'LEADER'"),
        ),
        Index("ix_team_members_team_id", "team_id"),
        Index("ix_team_members_student_id", "student_id"),
    )
