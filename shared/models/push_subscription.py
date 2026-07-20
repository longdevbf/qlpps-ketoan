"""shared.push_subscriptions — Web Push subscription per device per user.

1 user có thể có N subscription (mỗi browser/thiết bị 1 row).
endpoint là URL push service (FCM/APNs/Mozilla) — UNIQUE để upsert idempotent.

Lifecycle:
- INSERT khi user bấm "Bật thông báo" → browser trả {endpoint, keys.p256dh, keys.auth}
- DELETE khi pywebpush báo HTTP 410 Gone (subscription expired) hoặc user gỡ thủ công
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    __table_args__ = (
        Index("ix_push_sub_username", "username"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512))
    source_app: Mapped[Optional[str]] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
