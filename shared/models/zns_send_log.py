"""ZNSSendLog — lưu lịch sử mọi lần gửi ZNS qua Zalo OA.

1 row mỗi lần gọi API. status: sent | failed | invalid_phone | skipped.
Dùng cho admin dashboard tỉ lệ thành công + quota tracking.
"""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class ZNSSendLog(Base):
    __tablename__ = "zns_send_log"
    __table_args__ = ({"schema": "shared"},)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ref_type: Mapped[str] = mapped_column(String(32), nullable=False)        # lead | quote | order | manual
    ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    template_key: Mapped[Optional[str]] = mapped_column(String(64))         # welcome_lead | quote_approved
    params: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False)         # sent | failed | invalid_phone
    error_code: Mapped[Optional[int]] = mapped_column(Integer)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    zalo_msg_id: Mapped[Optional[str]] = mapped_column(String(64))
    response: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    quota_remaining: Mapped[Optional[int]] = mapped_column(Integer)
    triggered_by: Mapped[Optional[str]] = mapped_column(String(64))
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
