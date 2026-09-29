"""TamUng + TamUngQuyetToan — tạm ứng nhân viên (TK 141) và các lần quyết toán.

Trước 2026-09-25 hệ thống KHÔNG có nơi nào lưu tạm ứng nhân viên (đã rà
ketoan.so_quy / chi_phi_phat_sinh / journal / saleadmin.denghitt /
shared.expense_requests / hcns — không có TK 141, không có bảng tạm ứng).

Hạch toán (services/tam_ung.py, qua services/journal.py:post_journal):
  - Chi tạm ứng:   Nợ 141 / Có 111|112            + 1 dòng so_quy chi
  - Quyết toán:    Nợ 641|642|635|811 (chi thực tế) / Có 141
                   thừa → Nợ 111|112 (nộp lại, + so_quy thu) hoặc Nợ 334 (trừ lương)
                   thiếu → Có 111|112 (chi bù, + so_quy chi)
  - Xoá / huỷ:     void_journal (bút toán đảo) + xoá dòng so_quy tương ứng.

Bảng tạo bởi `services/tam_ung_schema.py:ensure_schema()` (DDL idempotent).
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from shared.db import Base


class TamUng(Base):
    __tablename__ = "tam_ung"
    __table_args__ = ({"schema": "ketoan"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    so_ct: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    ngay: Mapped[date] = mapped_column(Date, nullable=False)
    nhan_vien_ma: Mapped[str] = mapped_column(String(16), nullable=False)
    nhan_vien_ten: Mapped[str] = mapped_column(String(255), nullable=False)
    noi_dung: Mapped[str] = mapped_column(Text, nullable=False)
    so_tien: Mapped[Decimal] = mapped_column(Numeric(15, 0), nullable=False)
    han_hoan: Mapped[date] = mapped_column(Date, nullable=False)
    tai_khoan_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("ketoan.tai_khoan_nh.id", ondelete="SET NULL"),
    )
    tai_khoan_ten: Mapped[Optional[str]] = mapped_column(String(255))
    tk_tien: Mapped[str] = mapped_column(String(10), nullable=False)  # '111' | '112'
    journal_id: Mapped[Optional[int]] = mapped_column(Integer)
    so_quy_id: Mapped[Optional[int]] = mapped_column(Integer)
    # hieu_luc | da_huy
    trang_thai: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="hieu_luc",
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_by: Mapped[Optional[str]] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    quyet_toans: Mapped[list["TamUngQuyetToan"]] = relationship(
        "TamUngQuyetToan", back_populates="tam_ung", lazy="selectin",
        order_by="TamUngQuyetToan.id",
    )


class TamUngQuyetToan(Base):
    __tablename__ = "tam_ung_quyet_toan"
    __table_args__ = ({"schema": "ketoan"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tam_ung_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ketoan.tam_ung.id", ondelete="CASCADE"), nullable=False,
    )
    so_ct: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    ngay: Mapped[date] = mapped_column(Date, nullable=False)
    chi_phi: Mapped[Decimal] = mapped_column(Numeric(15, 0), nullable=False, server_default="0")
    tk_cp: Mapped[Optional[str]] = mapped_column(String(10))
    hoan: Mapped[Decimal] = mapped_column(Numeric(15, 0), nullable=False, server_default="0")
    chi_bu: Mapped[Decimal] = mapped_column(Numeric(15, 0), nullable=False, server_default="0")
    xu_ly_thua: Mapped[Optional[str]] = mapped_column(String(20))  # thu_tien | tru_luong
    giam_tam_ung: Mapped[Decimal] = mapped_column(Numeric(15, 0), nullable=False)  # số ghi Có 141
    ket_thuc: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    journal_id: Mapped[Optional[int]] = mapped_column(Integer)
    so_quy_id: Mapped[Optional[int]] = mapped_column(Integer)
    chi_phi_id: Mapped[Optional[int]] = mapped_column(Integer)
    trang_thai: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="hieu_luc",
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    tam_ung: Mapped[TamUng] = relationship("TamUng", back_populates="quyet_toans")
