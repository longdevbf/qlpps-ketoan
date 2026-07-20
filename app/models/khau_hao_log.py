"""KhauHaoLog — nhật ký khấu hao tháng (Phase 3).

Mỗi TSCĐ × tháng = 1 dòng. UNIQUE(tscd_id, thang) để không khấu hao
2 lần cùng tháng. Có `journal_id` ref tới `journal_entry` (bút toán
Nợ 641|642|635|811 / Có 214 sinh khi chạy khấu hao).
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String,
    Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from shared.db import Base


class KhauHaoLog(Base):
    __tablename__ = "khau_hao_log"
    __table_args__ = (
        UniqueConstraint("tscd_id", "thang", name="uq_kh_tscd_thang"),
        CheckConstraint("so_tien > 0", name="ck_kh_so_tien_pos"),
        Index("ix_kh_thang", "thang"),
        Index("ix_kh_tscd", "tscd_id"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tscd_id: Mapped[int] = mapped_column(
        ForeignKey("ketoan.tai_san_co_dinh.id", ondelete="CASCADE"),
        nullable=False,
    )
    thang: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    so_tien: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    hao_mon_luy_ke_sau: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False
    )
    journal_id: Mapped[Optional[int]] = mapped_column(Integer)
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tscd: Mapped["TaiSanCoDinh"] = relationship(
        "TaiSanCoDinh", back_populates="khau_hao_logs",
    )

    def __repr__(self) -> str:
        return (
            f"<KhauHaoLog {self.id} tscd={self.tscd_id} "
            f"{self.thang} {self.so_tien}>"
        )
