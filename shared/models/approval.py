"""Approvals — phê duyệt vượt ngưỡng do CEO duyệt.

Mỗi app dept khi tạo bản ghi vượt ngưỡng → INSERT 1 row vào shared.approvals
+ emit_event("approval:new"). CEO mở inbox → approve/reject → app dept lắng
"approval:done" → áp dụng kết quả.

kind ví dụ:
    'baogia.quote_high_value'      payload: {quote_id, customer_id, tong_tien}
    'muahang.po_high_value'        payload: {po_id, ncc_id, tong_tien}
    'marketing.km_deep_discount'   payload: {km_id, percent}
    'hcns.salary_increase'         payload: {employee_id, old, new}
    'muahang.ncc_new'              payload: {ncc_id, ten}
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, BigInteger, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        Index("ix_approvals_status", "status"),
        Index("ix_approvals_app_status", "app", "status"),
        Index("ix_approvals_kind", "kind"),
        Index("ix_approvals_created", "created_at"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    app: Mapped[str] = mapped_column(String(32), nullable=False)
    ref_id: Mapped[Optional[str]] = mapped_column(String(64))
    payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    requested_by: Mapped[Optional[str]] = mapped_column(String(64))
    requested_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shared.users.id"))
    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    approved_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shared.users.id"))
    comment: Mapped[Optional[str]] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
