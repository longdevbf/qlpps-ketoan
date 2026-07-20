"""JournalEntry — header bút toán kế toán (double-entry).

Mỗi nghiệp vụ CRUD manual (góp vốn, chi phí, nhập kho, vay, ...) đẻ ra 1
journal_entry với nhiều journal_line (≥ 2: 1 nợ + 1 có) sao cho
SUM(no.so_tien) ≈ SUM(co.so_tien).
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Date, DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from shared.db import Base


class JournalEntry(Base):
    __tablename__ = "journal_entry"
    __table_args__ = (
        UniqueConstraint("ma_but_toan", name="uq_je_ma_but_toan"),
        Index("ix_je_ngay", "ngay"),
        Index("ix_je_source", "source_type", "source_id"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ma_but_toan: Mapped[str] = mapped_column(String(32), nullable=False)  # 'BT-2026-0001'
    ngay: Mapped[date] = mapped_column(Date, nullable=False)
    mo_ta: Mapped[Optional[str]] = mapped_column(Text)
    # gop_von | rut_von | chia_co_tuc | trich_quy | chi_phi_phat_sinh
    # | chi_phi_co_dinh | nhap_kho_manual | xuat_kho_manual
    # | tao_khoan_vay | tra_no_vay | tk_nh_thu | tk_nh_chi
    # | reversal_of_<...> | other
    source_type: Mapped[Optional[str]] = mapped_column(String(40))
    source_id: Mapped[Optional[str]] = mapped_column(String(64))
    tong_tien: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    # du_thao | da_post | da_huy
    trang_thai: Mapped[str] = mapped_column(
        String(20), server_default="da_post", nullable=False,
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    lines: Mapped[list["JournalLine"]] = relationship(
        "JournalLine",
        back_populates="entry",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<JournalEntry {self.id} {self.ma_but_toan} "
            f"{self.source_type} {self.tong_tien}>"
        )
