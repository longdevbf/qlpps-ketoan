"""QuyDN — danh mục quỹ doanh nghiệp dạng cây.

Source compute:
- doanh_thu_pct: ty_le_pct% × DT thực tế tháng
- parent_pct:    ty_le_pct% × thành tiền parent (cùng tháng)
- hcns_cong_doan: đọc từ HCNS API
- manual:        nhập tay
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class QuyDN(Base):
    __tablename__ = "quy_dn"
    __table_args__ = (
        UniqueConstraint("ten_quy", name="uq_quy_dn_ten"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ten_quy: Mapped[str] = mapped_column(String(128), nullable=False)
    so_du: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False,
    )
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False,
    )

    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("ketoan.quy_dn.id", ondelete="CASCADE"), nullable=True,
    )
    nguon_compute: Mapped[str] = mapped_column(
        String(32), server_default="manual", nullable=False,
    )
    ty_le_pct: Mapped[Decimal] = mapped_column(
        Numeric(7, 4), server_default="0", nullable=False,
    )
    thu_tu: Mapped[int] = mapped_column(
        Integer, server_default="0", nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<QuyDN {self.id} {self.ten_quy!r} so_du={self.so_du}>"
