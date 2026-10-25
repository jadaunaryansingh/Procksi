from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class RevokedToken(Base):
    """
    Stores JTI (JWT ID) of access tokens that have been explicitly revoked
    (i.e. the admin logged out before the token expired).

    On every authenticated request, the JTI from the incoming token is checked
    against this table. If found, the request is rejected with 401.

    Expired entries should be purged periodically — they carry no security value
    once the token's own `exp` has passed.
    """

    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID string
    revoked_at: Mapped[datetime] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)  # for future cleanup job
