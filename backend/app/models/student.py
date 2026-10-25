import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Index, func, UUID, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.enums import StudentStatus
class Student(Base):
    __tablename__ = "students"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)
    branch: Mapped[str] = mapped_column(String(100), nullable=False)
    section: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(StudentStatus, nullable=False, default="active")
    semester_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("semester_config.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    semester: Mapped[Optional["SemesterConfig"]] = relationship(
        "SemesterConfig", lazy="select"
    )
    team_membership: Mapped[Optional["TeamMember"]] = relationship(
        "TeamMember", back_populates="student", lazy="select", uselist=False
    )

    __table_args__ = (
        Index("ix_students_student_id", "student_id"),
        Index("ix_students_email", "email"),
    )
