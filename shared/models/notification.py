"""shared.notifications — bảng noti dùng chung 3 app (baogia/marketing/muahang).

Pattern fan-out: 1 event → tạo N row, mỗi row 1 user nhận. Đọc đơn giản
WHERE target_username = me, không cần resolve role lúc đọc.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Index, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "ix_noti_target_seen_created",
            "target_username", "seen", "created_at",
        ),
        Index("ix_noti_ref", "ref_type", "ref_id"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_username: Mapped[str] = mapped_column(String(64), nullable=False)
    source_app: Mapped[str] = mapped_column(String(16), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text)
    ref_type: Mapped[Optional[str]] = mapped_column(String(32))
    ref_id: Mapped[Optional[str]] = mapped_column(String(64))
    url: Mapped[Optional[str]] = mapped_column(String(512))
    severity: Mapped[str] = mapped_column(
        String(16), default="info", server_default="info", nullable=False,
    )
    seen: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False,
    )
    seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
