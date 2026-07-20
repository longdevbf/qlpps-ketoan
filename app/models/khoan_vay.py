"""KhoanVay — quản lý vốn vay (3 bảng).

- KhoanVay: master 1 khoản vay (mã, nguồn, số tiền, kỳ hạn, phương thức trả, status).
- KhoanVayLaiSuat: lịch sử lãi suất % năm (đổi theo từng giai đoạn — NH thay đổi).
- KhoanVayGiaoDich: nhật ký giao dịch (giải ngân, trả gốc, trả lãi, trả gốc+lãi).
  Mỗi giao dịch link sang `so_quy` (tiền vào/ra) và optionally `chi_phi_phat_sinh` (lãi).
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from shared.db import Base


class KhoanVay(Base):
    __tablename__ = "khoan_vay"
    __table_args__ = (
        UniqueConstraint("ma_khoan", name="uq_khoan_vay_ma"),
        Index("ix_kv_status", "status"),
        Index("ix_kv_nguon", "nguon_vay"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ma_khoan: Mapped[str] = mapped_column(String(64), nullable=False)
    nguon_vay: Mapped[str] = mapped_column(String(128), nullable=False)
    # tin_chap | the_chap | tra_gop_xe | tra_gop_nha | khac
    loai_vay: Mapped[str] = mapped_column(String(32), nullable=False, default="tin_chap")

    so_tien_vay: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    ngay_vay: Mapped[date] = mapped_column(Date, nullable=False)
    ky_han_thang: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    ngay_dao_han: Mapped[Optional[date]] = mapped_column(Date)

    # tu_do | tra_deu | chi_lai_dinh_ky | goc_lai_cuoi_ky
    phuong_thuc_tra: Mapped[str] = mapped_column(String(32), nullable=False, default="tu_do")
    tai_san_the_chap: Mapped[Optional[str]] = mapped_column(Text)
    tai_khoan_giai_ngan: Mapped[Optional[str]] = mapped_column(String(128))

    # dang_vay | da_tat_toan | qua_han
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="dang_vay")
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lai_suats: Mapped[list["KhoanVayLaiSuat"]] = relationship(
        "KhoanVayLaiSuat", back_populates="khoan_vay",
        cascade="all, delete-orphan", order_by="KhoanVayLaiSuat.tu_ngay",
    )
    giao_dichs: Mapped[list["KhoanVayGiaoDich"]] = relationship(
        "KhoanVayGiaoDich", back_populates="khoan_vay",
        cascade="all, delete-orphan", order_by="KhoanVayGiaoDich.ngay",
    )


class KhoanVayLaiSuat(Base):
    __tablename__ = "khoan_vay_lai_suat"
    __table_args__ = (
        Index("ix_kvls_khoan_tu_ngay", "khoan_vay_id", "tu_ngay"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    khoan_vay_id: Mapped[int] = mapped_column(
        ForeignKey("ketoan.khoan_vay.id", ondelete="CASCADE"), nullable=False
    )
    tu_ngay: Mapped[date] = mapped_column(Date, nullable=False)
    lai_suat_nam: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    khoan_vay: Mapped["KhoanVay"] = relationship("KhoanVay", back_populates="lai_suats")


class KhoanVayGiaoDich(Base):
    __tablename__ = "khoan_vay_giao_dich"
    __table_args__ = (
        Index("ix_kvgd_khoan_loai", "khoan_vay_id", "loai"),
        Index("ix_kvgd_ngay", "ngay"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    khoan_vay_id: Mapped[int] = mapped_column(
        ForeignKey("ketoan.khoan_vay.id", ondelete="CASCADE"), nullable=False
    )
    # giai_ngan | tra_goc | tra_lai | tra_goc_lai | phat
    loai: Mapped[str] = mapped_column(String(32), nullable=False)
    ngay: Mapped[date] = mapped_column(Date, nullable=False)
    so_tien: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    so_tien_goc: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    so_tien_lai: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    ref_so_quy_id: Mapped[Optional[int]] = mapped_column(Integer)
    ref_chi_phi_id: Mapped[Optional[int]] = mapped_column(Integer)
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    khoan_vay: Mapped["KhoanVay"] = relationship("KhoanVay", back_populates="giao_dichs")
