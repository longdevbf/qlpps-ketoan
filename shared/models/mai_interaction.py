"""MaiInteraction + NVActivity — log per-NV behavior cho dashboard CEO."""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class MaiInteraction(Base):
    __tablename__ = "mai_interaction"
    __table_args__ = ({"schema": "shared"},)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    room_id: Mapped[Optional[int]] = mapped_column(Integer)
    chat_message_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    category: Mapped[Optional[str]] = mapped_column(String(32))
    intent: Mapped[Optional[str]] = mapped_column(String(64))
    tools_used: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    tokens_in: Mapped[Optional[int]] = mapped_column(Integer)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer)
    cost_usd: Mapped[Optional[float]] = mapped_column(Numeric(10, 5))
    outcome: Mapped[Optional[str]] = mapped_column(String(32))
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    satisfaction: Mapped[Optional[str]] = mapped_column(String(16))
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NVActivity(Base):
    __tablename__ = "nv_activity"
    __table_args__ = ({"schema": "shared"},)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    app: Mapped[Optional[str]] = mapped_column(String(32))
    ref_type: Mapped[Optional[str]] = mapped_column(String(32))
    ref_id: Mapped[Optional[str]] = mapped_column(String(64))
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSONB)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
