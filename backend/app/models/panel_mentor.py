import uuid
from sqlalchemy import ForeignKey, UUID, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class PanelMentor(Base):
    __tablename__ = "panel_mentors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    panel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("panels.id"), nullable=False)
    mentor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mentors.id"), nullable=False)

    panel: Mapped["Panel"] = relationship(
        "Panel", back_populates="panel_mentors", lazy="select"
    )
    mentor: Mapped["Mentor"] = relationship(
        "Mentor", back_populates="panel_memberships", lazy="select"
    )
    
    __table_args__ = (
        Index("ix_panel_mentors_mentor_id", "mentor_id"),
        Index("ix_panel_mentors_panel_id", "panel_id"),
        Index("uq_panel_mentor", "panel_id", "mentor_id", unique=True),
    )
