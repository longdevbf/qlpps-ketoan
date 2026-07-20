"""shared.mobile_devices — FCM token per native mobile device per user.

Khác PushSubscription (web push qua VAPID): bảng này lưu FCM token thuần để
gửi data message từ chat backend → app native → tạo full-screen incoming
call như Zalo khi app đóng.

Lifecycle:
- UPSERT khi mobile app gọi POST /api/chat/devices/register-fcm sau login
- Mark inactive khi FCM trả 404/NOT_REGISTERED (token rotate / app gỡ)
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class MobileDevice(Base):
    __tablename__ = "mobile_devices"
    __table_args__ = (
        Index("ix_mobile_devices_username", "username"),
        Index("ix_mobile_devices_active", "active"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    fcm_token: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    platform: Mapped[str] = mapped_column(String(16), nullable=False, default="android")
    app_version: Mapped[Optional[str]] = mapped_column(String(40))
    device_model: Mapped[Optional[str]] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
