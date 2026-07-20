from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import INET, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class Session(Base):
    """Refresh token sessions — track issued/revoked JWT IDs."""
    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_user", "user_id"),
        Index("ix_sessions_expires", "expires_at"),
        {"schema": "shared"},
    )

    jti: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("shared.users.id", ondelete="CASCADE"), nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ip: Mapped[Optional[str]] = mapped_column(INET)
    ua: Mapped[Optional[str]] = mapped_column(String(512))
