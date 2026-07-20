"""SepayTransaction — audit trail giao dịch SePay webhook.

Mỗi payload SePay POST về `/api/sepay/webhook` → insert 1 record.
- `sepay_id` UNIQUE chống double credit khi SePay retry.
- `status='matched'` → có so_quy_id + quote_number ghi vào sổ quỹ.
- `status='orphan'` → memo không parse được / quote_number không tồn tại;
  KT xử lý tay trong trang "Giao dịch SePay".
- `status='ignored'` → KT confirm không phải Papasan (bỏ qua).
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import String, Numeric, DateTime, Integer, Text, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class SepayTransaction(Base):
    __tablename__ = "sepay_transactions"
    __table_args__ = (
        Index("ix_sepay_txn_sepay_id", "sepay_id", unique=True),
        Index("ix_sepay_txn_quote", "quote_number"),
        Index("ix_sepay_txn_status", "status"),
        Index("ix_sepay_txn_created", "created_at"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sepay_id: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    gateway: Mapped[Optional[str]] = mapped_column(String(64))
    account_number: Mapped[Optional[str]] = mapped_column(String(64))
    transfer_type: Mapped[Optional[str]] = mapped_column(String(8))  # 'in' | 'out'
    amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )
    content: Mapped[Optional[str]] = mapped_column(Text)
    reference_code: Mapped[Optional[str]] = mapped_column(String(64))
    raw_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)

    quote_number: Mapped[Optional[str]] = mapped_column(String(64))
    so_quy_id: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(16), server_default="matched", nullable=False
    )
    matched_by: Mapped[Optional[str]] = mapped_column(String(64))
    matched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    note: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<SepayTxn id={self.id} sepay={self.sepay_id} "
            f"amt={self.amount} qn={self.quote_number} st={self.status}>"
        )
