"""VonCSH — vốn chủ sở hữu (gop_von / rut_von / chia_co_tuc / trich_quy / dieu_chinh)."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class VonCSH(Base):
    __tablename__ = "von_chu_so_huu"
    __table_args__ = (
        Index("ix_voncsh_ngay", "ngay"),
        Index("ix_voncsh_loai", "loai_giao_dich"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ngay: Mapped[date] = mapped_column(Date, nullable=False)
    # gop_von | rut_von | chia_co_tuc | trich_quy | dieu_chinh
    loai_giao_dich: Mapped[str] = mapped_column(String(20), nullable=False)
    so_tien: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    chu_so_huu: Mapped[Optional[str]] = mapped_column(String(128))
    quy_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ketoan.quy_dn.id", ondelete="SET NULL"), nullable=True,
    )
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    source_doc_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<VonCSH {self.id} {self.ngay} {self.loai_giao_dich} {self.so_tien}>"
        )
