import uuid
from datetime import datetime
from sqlalchemy import String, Text, ForeignKey, Index, func, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("admins.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    admin: Mapped["Admin"] = relationship(
        "Admin", back_populates="audit_logs", lazy="select"
    )

    __table_args__ = (Index("ix_audit_logs_admin_id", "admin_id"),)
