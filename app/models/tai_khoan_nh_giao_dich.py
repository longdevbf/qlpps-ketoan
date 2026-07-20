"""TaiKhoanNHGiaoDich — nhật ký thu/chi từng tài khoản ngân hàng.

Số dư TK = SUM(thu) - SUM(chi). Bỏ pattern lưu cột so_du cứng.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class TaiKhoanNHGiaoDich(Base):
    __tablename__ = "tai_khoan_nh_giao_dich"
    __table_args__ = (
        Index("ix_tknh_gd_ngay", "ngay"),
        Index("ix_tknh_gd_tk", "tai_khoan_id"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ngay: Mapped[date] = mapped_column(Date, nullable=False)
    tai_khoan_id: Mapped[int] = mapped_column(
        ForeignKey("ketoan.tai_khoan_nh.id", ondelete="CASCADE"), nullable=False,
    )
    # 'thu' | 'chi'
    loai: Mapped[str] = mapped_column(String(10), nullable=False)
    so_tien: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    doi_tac: Mapped[Optional[str]] = mapped_column(String(255))
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    source_app: Mapped[Optional[str]] = mapped_column(String(32))
    source_doc_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<TaiKhoanNHGiaoDich {self.id} tk={self.tai_khoan_id} "
            f"{self.loai} {self.so_tien}>"
        )
