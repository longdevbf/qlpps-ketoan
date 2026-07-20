"""BaoCaoPLSnapshot — snapshot báo cáo P&L theo tháng (chuẩn mực kế toán).

10 chỉ tiêu: dt_thuan, cogs, ln_gop, cp_ban_hang, cp_quan_ly, dt_tai_chinh,
cp_tai_chinh, thu_nhap_khac, cp_khac, ln_truoc_thue, thue_tndn, lnst.

`thang` VARCHAR(7) định dạng 'YYYY-MM' (UNIQUE).
`raw_breakdown` JSONB lưu thêm chi tiết breakdown cho audit/UI.

KHÔNG đụng `bao_cao_snapshot.py` cũ (bảng khác — full P&L tổng hợp legacy).
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class BaoCaoPLSnapshot(Base):
    __tablename__ = "bao_cao_pl_snapshot"
    __table_args__ = ({"schema": "ketoan"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thang: Mapped[str] = mapped_column(String(7), nullable=False, unique=True)

    dt_thuan: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    cogs: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    ln_gop: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    cp_ban_hang: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    cp_quan_ly: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    dt_tai_chinh: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    cp_tai_chinh: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    thu_nhap_khac: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    cp_khac: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    ln_truoc_thue: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    thue_tndn: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    lnst: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))

    raw_breakdown: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<BaoCaoPLSnapshot {self.id} {self.thang} lnst={self.lnst}>"
