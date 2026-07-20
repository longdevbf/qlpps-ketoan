"""SoDuDauKy — số dư đầu kỳ theo tháng × tài khoản.

Dùng để tính P&L tổng hợp + đối chiếu sổ quỹ. UNIQUE (thang, tai_khoan_id).
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Date, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class SoDuDauKy(Base):
    __tablename__ = "so_du_dau_ky"
    __table_args__ = (
        UniqueConstraint("thang", "tai_khoan_id", name="uq_sddk_thang_tk"),
        Index("ix_sddk_thang", "thang"),  # ASC index — DESC chỉ matter khi ORDER BY
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thang: Mapped[date] = mapped_column(Date, nullable=False)  # yyyy-mm-01
    tai_khoan_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("ketoan.tai_khoan_nh.id", ondelete="SET NULL"),
        nullable=True,
    )
    so_du: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<SoDuDauKy {self.id} {self.thang} tk={self.tai_khoan_id} {self.so_du}>"
