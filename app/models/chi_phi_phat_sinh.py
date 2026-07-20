"""ChiPhiPhatSinh — chi phí phát sinh hàng ngày (port từ `KT_ChiPhiPhatSinh` + chi_phi.json)."""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Numeric, DateTime, Date, Integer, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class ChiPhiPhatSinh(Base):
    __tablename__ = "chi_phi_phat_sinh"
    __table_args__ = (
        Index("ix_cpps_ngay", "ngay"),
        Index("ix_cpps_loai", "loai_chi_phi"),
        Index("ix_cpps_ref_vc", "ref_vc"),
        Index("ix_cpps_nhom", "nhom_chi_phi"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ngay: Mapped[date] = mapped_column(Date, nullable=False)
    so_tien: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )                                                               # 'tong_chi' V1
    loai_chi_phi: Mapped[Optional[str]] = mapped_column(String(128))  # FK loose ketoan.loai_chi_phi.ten
    ten_khoan: Mapped[Optional[str]] = mapped_column(String(255))     # Tên cụ thể vd "Mua văn phòng phẩm tháng 4"
    # Phân nhóm chức năng cho P&L: 'ban_hang' | 'quan_ly' | 'tai_chinh' | 'khac'
    nhom_chi_phi: Mapped[str] = mapped_column(
        String(20), server_default="khac", nullable=False
    )
    quy: Mapped[Optional[str]] = mapped_column(String(64))            # 'Quỹ Công Ty', 'Quỹ Riêng',...
    phong_ban: Mapped[Optional[str]] = mapped_column(String(128))
    nguoi_chi: Mapped[Optional[str]] = mapped_column(String(128))
    don_vi_vc: Mapped[Optional[str]] = mapped_column(String(128))     # đơn vị vận chuyển (legacy V1)
    ma_don: Mapped[Optional[str]] = mapped_column(String(64))
    ngan_hang: Mapped[Optional[str]] = mapped_column(String(128))     # FK loose ketoan.tai_khoan_nh.ten_tk
    hoa_don_url: Mapped[Optional[str]] = mapped_column(String(512))   # Drive file url
    mo_ta: Mapped[Optional[str]] = mapped_column(Text)
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)

    # Auto-create từ saleadmin.vanchuyen.ma_vh — partial UNIQUE WHERE ref_vc IS NOT NULL
    ref_vc: Mapped[Optional[str]] = mapped_column(String(32))

    # Bridge marketing.ads_cost → 1 row/(tháng × kênh). Format: 'ADS-{thang}-{kenh}'.
    ref_ads_thang_kenh: Mapped[Optional[str]] = mapped_column(String(64))
    # Bridge hcns.payroll → 1 row/(tháng × phòng ban). Format: 'PAYROLL-{thang}-{phong_ban_slug}'.
    ref_payroll_thang_pb: Mapped[Optional[str]] = mapped_column(String(96))
    # Bridge saleadmin.phatsinh (đã xử lý) → 1 row. Format: 'PS-{id}'. Partial UNIQUE.
    ref_phatsinh: Mapped[Optional[str]] = mapped_column(String(32))
    # Bridge saleadmin.denghitt (CEO duyệt) → 1 row. Format: 'DNTT-{id}'. Partial UNIQUE.
    ref_dntt: Mapped[Optional[str]] = mapped_column(String(32))

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

    def __repr__(self) -> str:
        return f"<ChiPhiPhatSinh {self.id} {self.ngay} {self.so_tien}>"
