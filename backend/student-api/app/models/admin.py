import uuid
from datetime import datetime
from sqlalchemy import String, func, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.enums import AdminRole


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(AdminRole, nullable=False, default="ADMIN")
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now(), nullable=False
    )

    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="admin", lazy="select"
    )
    email_logs: Mapped[list["EmailLog"]] = relationship(
        "EmailLog", back_populates="sender", lazy="select"
    )
