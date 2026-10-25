import uuid
from typing import Optional
from sqlalchemy import String, Index, UUID, Text, Integer
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
class Mentor(Base):
    __tablename__ = "mentors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    expertise: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=[])
    domains: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=[])
    experience_years: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_teams: Mapped[int] = mapped_column(default=3, nullable=False)
    current_teams: Mapped[int] = mapped_column(default=0, nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(JSONB, nullable=True)

    teams: Mapped[list["Team"]] = relationship(
        "Team", back_populates="mentor", lazy="select"
    )
    panel_memberships: Mapped[list["PanelMentor"]] = relationship(
        "PanelMentor", back_populates="mentor", lazy="select"
    )

    __table_args__ = ()
