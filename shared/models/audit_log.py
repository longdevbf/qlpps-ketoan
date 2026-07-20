from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, BigInteger, ForeignKey, Index
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_ts", "ts"),
        Index("ix_audit_user_ts", "user_id", "ts"),
        Index("ix_audit_action", "action"),
        Index("ix_audit_app", "app"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    app: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shared.users.id"))
    username: Mapped[Optional[str]] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[Optional[str]] = mapped_column(String(255))
    ip: Mapped[Optional[str]] = mapped_column(INET)
    ua: Mapped[Optional[str]] = mapped_column(String(512))
    payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="ok", nullable=False)
