"""QuyDNGiaoDich — log thu/chi quỹ doanh nghiệp.

Mọi thay đổi `quy_dn.so_du` đi qua bảng này (audit trail).
Service `quy_dn_calc` chịu trách nhiệm insert + cập nhật so_du atomically.
"""
from datetime import date as date_cls, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class QuyDNGiaoDich(Base):
    __tablename__ = "quy_dn_giao_dich"
    __table_args__ = (
        CheckConstraint("loai IN ('thu','chi')", name="ck_qdgd_loai"),
        CheckConstraint("so_tien > 0", name="ck_qdgd_so_tien_pos"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quy_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ketoan.quy_dn.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ngay: Mapped[date_cls] = mapped_column(Date, nullable=False, index=True)
    loai: Mapped[str] = mapped_column(String(10), nullable=False)  # 'thu' | 'chi'
    so_tien: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    noi_dung: Mapped[Optional[str]] = mapped_column(Text)
    source_type: Mapped[Optional[str]] = mapped_column(String(32))
    # 'manual' | 'trich_quy' | 'chi_phi' | 'hoan_quy' | 'dieu_chinh' | 'khac'
    source_id: Mapped[Optional[str]] = mapped_column(String(64))
    tai_khoan_id: Mapped[Optional[int]] = mapped_column(Integer)
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<QuyDNGiaoDich {self.id} quy={self.quy_id} "
            f"{self.loai}={self.so_tien} {self.ngay}>"
        )
