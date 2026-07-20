"""TaiSanCoDinh — master Tài Sản Cố Định (Phase 3).

DN SME phân phối thành phẩm: TSCĐ chủ yếu là showroom, xe vận chuyển,
máy móc, nội thất, phần mềm. Phương pháp khấu hao đường thẳng (straight-line).

Account TT200:
  - 211 TSCĐ hữu hình; 213 TSCĐ vô hình
  - 214 Hao mòn lũy kế (contra-asset, credit normal balance)
  - 641 CP bán hàng / 642 CP quản lý / 635 CP tài chính / 811 CP khác
    (xác định khi khấu hao theo `bo_phan`)
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint, Date, DateTime, Index, Integer, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from shared.db import Base


class TaiSanCoDinh(Base):
    __tablename__ = "tai_san_co_dinh"
    __table_args__ = (
        UniqueConstraint("ma_tscd", name="uq_tscd_ma"),
        CheckConstraint("nguyen_gia > 0", name="ck_tscd_nguyen_gia_pos"),
        CheckConstraint("so_thang_kh > 0", name="ck_tscd_so_thang_pos"),
        Index("ix_tscd_loai", "loai"),
        Index("ix_tscd_trang_thai", "trang_thai"),
        Index("ix_tscd_nhom", "nhom"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ma_tscd: Mapped[str] = mapped_column(String(32), nullable=False)
    ten_tscd: Mapped[str] = mapped_column(String(255), nullable=False)
    # huu_hinh | vo_hinh
    loai: Mapped[str] = mapped_column(
        String(20), nullable=False, default="huu_hinh"
    )
    nhom: Mapped[Optional[str]] = mapped_column(String(64))
    ngay_mua: Mapped[date] = mapped_column(Date, nullable=False)
    ngay_su_dung: Mapped[date] = mapped_column(Date, nullable=False)
    nguyen_gia: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    # Phần chi phí lắp đặt nằm trong nguyen_gia (tracking-only, không khấu hao riêng)
    chi_phi_lap_dat: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0"), server_default="0",
    )
    so_thang_kh: Mapped[int] = mapped_column(Integer, nullable=False)
    # duong_thang (default — SME) | (giảm dần) — chưa support
    phuong_phap: Mapped[str] = mapped_column(
        String(20), nullable=False, default="duong_thang"
    )
    hao_mon_luy_ke: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0"),
    )
    # 211 hữu hình | 213 vô hình
    account_code: Mapped[str] = mapped_column(
        String(20), nullable=False, default="211"
    )
    # ban_hang | quan_ly | tai_chinh | khac
    bo_phan: Mapped[str] = mapped_column(
        String(20), nullable=False, default="quan_ly"
    )
    ncc: Mapped[Optional[str]] = mapped_column(String(255))
    source_doc_id: Mapped[Optional[str]] = mapped_column(String(64))
    # dang_su_dung | da_thanh_ly | hong
    trang_thai: Mapped[str] = mapped_column(
        String(20), nullable=False, default="dang_su_dung"
    )
    ngay_thanh_ly: Mapped[Optional[date]] = mapped_column(Date)
    gia_thanh_ly: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    hinh_anh: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    khau_hao_logs: Mapped[list["KhauHaoLog"]] = relationship(
        "KhauHaoLog",
        back_populates="tscd",
        cascade="all, delete-orphan",
        order_by="KhauHaoLog.thang",
    )

    def __repr__(self) -> str:
        return (
            f"<TaiSanCoDinh {self.id} {self.ma_tscd!r} "
            f"{self.ten_tscd!r} {self.trang_thai}>"
        )
