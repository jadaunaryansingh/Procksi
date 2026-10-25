import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, ForeignKey, Index, func, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.enums import ProposalStatus


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    semester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semester_config.id"), nullable=False
    )  # denormalized for faster filtering
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    technology_stack: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    document_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    ai_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        ProposalStatus, nullable=False, default="pending"
    )
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    team: Mapped["Team"] = relationship("Team", back_populates="proposals", lazy="select")
    semester: Mapped["SemesterConfig"] = relationship(
        "SemesterConfig", back_populates="proposals", lazy="select"
    )

    __table_args__ = (
        Index("ix_proposals_team_id", "team_id"),
        Index("ix_proposals_semester_id", "semester_id"),
        Index("ix_proposals_status", "status"),
    )
