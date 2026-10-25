import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class RefreshToken(Base):
    """
    Stores a SHA-256 hash of the refresh token issued at login.

    The raw token is returned to the client and stored in sessionStorage.
    Only the hash lives in the DB — the raw value is never persisted,
    so a DB breach does not expose usable tokens.

    One admin can have at most one active refresh token. On re-login or
    refresh, the old record is replaced.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    admin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admins.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    admin: Mapped["Admin"] = relationship("Admin", lazy="select")  # type: ignore[name-defined]
