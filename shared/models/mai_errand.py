"""MaiErrand — CEO giao Mai DM nhân viên thay mình.

Workflow:
  1) CEO chat Mai: "Mai DM Long hỏi tiến độ task X giúp anh"
  2) Mai gọi tool `assign_errand(target='long', topic='...', instructions='...')`
     → INSERT row status='pending' + Mai mở DM với Long + gửi message đầu (round 1).
     → status='in_progress'.
  3) Long reply Mai → chat_hook fires Mai với context errand.
     Mai (qua errand prompt) đánh giá → 2 nhánh:
     - Đã đủ info → gọi tool `errand_close_and_report(id, report)`:
         status='done', report=summary, completed_at=NOW.
         Mai gửi DM CEO báo cáo.
     - Cần hỏi tiếp → gọi tool `errand_followup_to_nv(id, question)`:
         round +=1 (max 3), gửi message tiếp cho Long.
  4) CEO có thể /cancel khi đang chạy → status='cancelled'.
  5) Cron 24h timeout: errand không reply → status='timeout' + DM CEO báo lỗi.

Field:
  - target_username   : NV được giao việc
  - target_ho_ten     : hiển thị (snapshot)
  - topic             : 1 dòng, vd "Hỏi tiến độ task X"
  - instructions      : detail CEO yêu cầu, vd "Hỏi anh ấy còn vướng gì, deadline thực tế"
  - status            : pending | in_progress | done | cancelled | timeout | failed
  - rounds            : số lần Mai đã hỏi NV (1-based)
  - max_rounds        : default 3
  - dm_room_id        : ID room DM Mai ↔ NV
  - transcript        : JSONB list [{role, sender, content, at}, ...] backup chat
  - report            : Mai's summary gửi CEO khi done
  - report_sent_at    : khi Mai DM CEO báo cáo
"""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class MaiErrand(Base):
    __tablename__ = "mai_errand"
    __table_args__ = (
        Index("ix_mai_errand_ceo_status", "ceo_username", "status"),
        Index("ix_mai_errand_target_status", "target_username", "status"),
        Index("ix_mai_errand_status", "status"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    ceo_user_id: Mapped[Optional[int]] = mapped_column(Integer)
    ceo_username: Mapped[str] = mapped_column(String(64), nullable=False)

    target_username: Mapped[str] = mapped_column(String(64), nullable=False)
    target_ho_ten: Mapped[Optional[str]] = mapped_column(String(128))

    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    instructions: Mapped[Optional[str]] = mapped_column(Text)

    status: Mapped[str] = mapped_column(
        String(20), server_default="pending", default="pending", nullable=False
    )
    rounds: Mapped[int] = mapped_column(Integer, server_default="0", default=0, nullable=False)
    max_rounds: Mapped[int] = mapped_column(Integer, server_default="3", default=3, nullable=False)

    dm_room_id: Mapped[Optional[int]] = mapped_column(Integer)
    transcript: Mapped[Optional[list[dict]]] = mapped_column(JSONB)

    report: Mapped[Optional[str]] = mapped_column(Text)
    report_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
