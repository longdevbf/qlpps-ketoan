"""MaiAutoDecision — log mọi quyết định auto của Mai trong inbox_review.

Khác với `MaiInteraction` (log chat turn), bảng này log mỗi item Mai xét
trong vòng quét inbox: duyệt chi, xin nghỉ, BG, PO, KM, DNTT, lệnh đi đỏ.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class MaiAutoDecision(Base):
    __tablename__ = "mai_auto_decisions"
    __table_args__ = ({"schema": "shared"},)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ref_label: Mapped[Optional[str]] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    executed: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    exec_error: Mapped[Optional[str]] = mapped_column(Text)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    currency: Mapped[Optional[str]] = mapped_column(String(8))
    requested_by_username: Mapped[Optional[str]] = mapped_column(String(64))
    requested_by_name: Mapped[Optional[str]] = mapped_column(String(255))
    current_step: Mapped[Optional[str]] = mapped_column(String(32))
    reason: Mapped[Optional[str]] = mapped_column(Text)
    applicable_rules: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    gap: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    age_hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    dry_run: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    review_run_id: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
