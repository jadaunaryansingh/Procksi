import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey, UniqueConstraint, func, UUID, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

# Scores must be derived ONLY from the evaluations table via results/calculate.
# Manual overrides are restricted to SUPER_ADMIN only.
# Every override must be written to audit_logs in the same transaction.


class Result(Base):
    __tablename__ = "results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    proposal_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    mid_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    final_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    total_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    team: Mapped["Team"] = relationship("Team", back_populates="result", lazy="select")

    __table_args__ = (UniqueConstraint("team_id", name="uq_result_team"),)
