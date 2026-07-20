"""AIChatMessage — lịch sử chat giữa user và Mai (AI trợ lý)."""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, Integer, String, Text, DateTime, Numeric, Index
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class AIChatMessage(Base):
    __tablename__ = "ai_chat_message"
    __table_args__ = (
        Index("ix_ai_chat_user_time", "user_id", "created_at"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    brief_level: Mapped[str] = mapped_column(String(16), nullable=False)
    model_used: Mapped[Optional[str]] = mapped_column(String(64))
    tokens_in: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
