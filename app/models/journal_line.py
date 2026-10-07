"""JournalLine — chi tiết các dòng nợ/có trong 1 bút toán.

`account_code` theo TT200 (111/112/156/331/411/...). `ref_table` + `ref_id`
là soft FK trỏ về bảng nguồn (vd 'tai_khoan_nh', 'cong_no', 'inventory_balance',
'von_chu_so_huu', 'quy_dn', 'khoan_vay').

`doi_tuong_*` + `ma_don` (2026-10-01, migration q8) là chi tiết công nợ theo khách/NCC/nhân viên và
theo đơn để dựng sổ chi tiết 131/331/141 từ sổ cái; NULL ở mọi bút toán cũ (không backfill).
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    ForeignKey, Index, Integer, Numeric, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db import Base


class JournalLine(Base):
    __tablename__ = "journal_line"
    __table_args__ = (
        Index("ix_jl_journal", "journal_id"),
        Index("ix_jl_account", "account_code"),
        Index("ix_jl_ref", "ref_table", "ref_id"),
        # Sổ chi tiết: lọc theo TK rồi theo đối tượng (vd 131 của một khách).
        Index("ix_jl_account_doi_tuong", "account_code", "doi_tuong_ma"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_id: Mapped[int] = mapped_column(
        ForeignKey("ketoan.journal_entry.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 'no' | 'co'
    loai: Mapped[str] = mapped_column(String(10), nullable=False)
    account_code: Mapped[str] = mapped_column(String(20), nullable=False)
    account_name: Mapped[Optional[str]] = mapped_column(String(255))
    ref_table: Mapped[Optional[str]] = mapped_column(String(64))
    ref_id: Mapped[Optional[int]] = mapped_column(Integer)
    so_tien: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    # 'khach' | 'ncc' | 'nv'; doi_tuong_ma/ten = mã + tên khách/NCC/nhân viên; ma_don = mã đơn (vd NV26001-26-00110)
    doi_tuong_loai: Mapped[Optional[str]] = mapped_column(String(20))
    doi_tuong_ma: Mapped[Optional[str]] = mapped_column(String(64))
    doi_tuong_ten: Mapped[Optional[str]] = mapped_column(String(255))
    ma_don: Mapped[Optional[str]] = mapped_column(String(64))

    entry: Mapped["JournalEntry"] = relationship(
        "JournalEntry", back_populates="lines",
    )

    def __repr__(self) -> str:
        return (
            f"<JournalLine {self.id} J{self.journal_id} "
            f"{self.loai}/{self.account_code} {self.so_tien}>"
        )
