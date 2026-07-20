"""Directives — CEO giao việc / chỉ đạo trưởng phòng.

CEO mở Module 4 → giao 1 việc cho 1 user (trưởng phòng) trong 1 app cụ thể.
Trưởng phòng đăng nhập app dept của mình thấy được "chỉ đạo" mới qua badge.

Status (5 giá trị — migration 0032_directive_status_v2):
  assigned     — vừa giao, NV chưa start (có thể đã `acknowledged_at`)
  in_progress  — NV đã "Bắt đầu" / "Tiếp tục"
  blocked      — NV "Tạm dừng" (kèm blocked_reason)
  done         — NV "Hoàn thành" (đã có response)
  cancelled    — CEO/from_user huỷ task (legacy 'dropped')

Timestamps tracking:
  created_at       — lúc tạo
  acknowledged_at  — NV bấm "Đã nhận"
  started_at       — NV chuyển sang in_progress lần đầu
  blocked_at       — lần gần nhất bị pause
  last_activity_at — heartbeat mọi action (dùng tính days_silent)
  completed_at     — NV bấm "Hoàn thành"
  closed_at        — CEO force close / huỷ (legacy)
"""
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, DateTime, Date, BigInteger, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class Directive(Base):
    __tablename__ = "directives"
    __table_args__ = (
        Index("ix_directives_to_status", "to_user", "status"),
        Index("ix_directives_app", "app"),
        Index("ix_directives_due", "due_date"),
        Index("ix_directives_group", "group_id"),
        Index("ix_directives_last_activity", "last_activity_at"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Nhóm các Directive được tạo cùng 1 batch giao việc cho nhiều NV (UI gom thành 1 thẻ).
    # Null = task lẻ (legacy).
    group_id: Mapped[Optional[str]] = mapped_column(String(32))
    from_user: Mapped[str] = mapped_column(String(64), nullable=False)
    from_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shared.users.id"))
    to_user: Mapped[str] = mapped_column(String(64), nullable=False)
    to_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shared.users.id"))
    app: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="assigned", nullable=False)
    priority: Mapped[str] = mapped_column(String(8), default="med", nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    response: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # ── v2 status tracking (migration 0032) ───────────────────────────────
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    blocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
