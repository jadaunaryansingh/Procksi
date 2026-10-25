import uuid
from sqlalchemy import String, ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Panel(Base):
    __tablename__ = "panels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    semester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semester_config.id"), nullable=False
    )

    semester: Mapped["SemesterConfig"] = relationship(
        "SemesterConfig", back_populates="panels", lazy="select"
    )
    panel_mentors: Mapped[list["PanelMentor"]] = relationship(
        "PanelMentor", back_populates="panel", lazy="select"
    )
    schedules: Mapped[list["Schedule"]] = relationship(
        "Schedule", back_populates="panel", lazy="select"
    )
    evaluations: Mapped[list["Evaluation"]] = relationship(
        "Evaluation", back_populates="panel", lazy="select"
    )
