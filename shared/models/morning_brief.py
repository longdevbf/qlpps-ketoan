"""MorningBrief — AI brief sáng pre-compute mỗi ngày cho mỗi user.

Cấu trúc: orchestrator (ceo/app/ai_brief/) gọi 6 collectors → ghi vào bảng này.
Mọi app đọc qua endpoint /api/ai-brief (mount ở app CEO) để hiển thị
trong chat widget khi NV mở app lần đầu trong ngày.
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger, Integer, String, Text, Date, DateTime, Numeric,
    UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class MorningBrief(Base):
    __tablename__ = "morning_brief"
    __table_args__ = (
        UniqueConstraint("user_id", "brief_date", name="uq_morning_brief_user_date"),
        Index("ix_morning_brief_date", "brief_date"),
        Index("ix_morning_brief_username", "username"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    ho_ten: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    phong_ban: Mapped[Optional[str]] = mapped_column(String(128))

    brief_date: Mapped[date] = mapped_column(Date, nullable=False)
    brief_level: Mapped[str] = mapped_column(String(16), nullable=False)
    # employee | manager | ceo

    metrics: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    alerts: Mapped[list] = mapped_column(JSONB, server_default="[]", nullable=False)
    highlights: Mapped[list] = mapped_column(JSONB, server_default="[]", nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)

    model_used: Mapped[Optional[str]] = mapped_column(String(64))
    tokens_in: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), server_default="0", nullable=False
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    opened_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
