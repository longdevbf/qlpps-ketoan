"""KyKeToan — trạng thái đóng kỳ + LN giữ lại lũy kế.

Mỗi tháng 1 row, PK = `thang` VARCHAR(7) ('YYYY-MM').

trang_thai = 'dang_mo' | 'da_chot'
LN giữ lại cuối kỳ = LN đầu kỳ + LNST kỳ - cổ tức - trích quỹ
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class KyKeToan(Base):
    __tablename__ = "ky_ke_toan"
    __table_args__ = ({"schema": "ketoan"},)

    thang: Mapped[str] = mapped_column(String(7), primary_key=True)  # 'YYYY-MM'

    trang_thai: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="dang_mo",
    )  # 'dang_mo' | 'da_chot'

    chot_luc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    chot_boi: Mapped[Optional[str]] = mapped_column(String(64))

    pl_snapshot_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("ketoan.bao_cao_pl_snapshot.id", ondelete="SET NULL"),
        nullable=True,
    )

    ln_giu_lai_dau_ky: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), server_default="0",
    )
    lnst_ky: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    ln_giu_lai_cuoi_ky: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))

    co_tuc_da_chia: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), server_default="0",
    )
    trich_quy_ky: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), server_default="0",
    )

    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<KyKeToan {self.thang} {self.trang_thai} lncl={self.ln_giu_lai_cuoi_ky}>"
