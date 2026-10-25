import uuid
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Index, UUID, Text, Integer, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class Mentor(Base):
    __tablename__ = "mentors"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    expertise: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=[])
    domains: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=[])
    experience_years: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_teams: Mapped[int] = mapped_column(default=3, nullable=False)
    current_teams: Mapped[int] = mapped_column(default=0, nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(JSONB, nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    teams: Mapped[list["Team"]] = relationship(
        "Team", back_populates="mentor", lazy="select"
    )
    panel_memberships: Mapped[list["PanelMentor"]] = relationship(
        "PanelMentor", back_populates="mentor", lazy="select"
    )

    __table_args__ = ()

