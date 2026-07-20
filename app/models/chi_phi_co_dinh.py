"""ChiPhiCoDinh — chi phí cố định hàng tháng (port từ `KT_ChiPhiCoDinh` + chi_phi_co_dinh.json)."""
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import String, Numeric, DateTime, Date, Integer, Boolean, Text, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class ChiPhiCoDinh(Base):
    __tablename__ = "chi_phi_co_dinh"
    __table_args__ = (
        Index("ix_cpcd_thang", "thang_bat_dau"),
        Index("ix_cpcd_ngay_bat_dau", "ngay_bat_dau"),
        Index("ix_cpcd_loai", "loai_chi_phi"),
        Index("ix_cpcd_nhom", "nhom_chi_phi"),
        Index("ix_cpcd_method", "phuong_phap_phan_bo"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thang_bat_dau: Mapped[date] = mapped_column(Date, nullable=False)   # 'YYYY-MM-01' parsed từ V1 'thang' string (legacy)
    # Phase 5B: prorated theo ngày chính xác.
    # ngay_bat_dau (NOT NULL) — ngày thực sự bắt đầu áp dụng (vd 15/03/2026)
    # ngay_ket_thuc (NULL = vô thời hạn) — ngày cuối cùng áp dụng (kết hợp lap_lai)
    ngay_bat_dau: Mapped[date] = mapped_column(Date, nullable=False)
    ngay_ket_thuc: Mapped[Optional[date]] = mapped_column(Date)
    so_tien_thang: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )                                                                    # 'thanh_tien' V1
    loai_chi_phi: Mapped[Optional[str]] = mapped_column(String(128))    # FK loose ketoan.loai_chi_phi.ten
    ten_khoan: Mapped[Optional[str]] = mapped_column(String(255))       # Tên cụ thể vd "Thuê showroom Q3 — 4/2026"
    # Phân nhóm chức năng cho P&L: 'ban_hang' | 'quan_ly' | 'tai_chinh' | 'khac'
    nhom_chi_phi: Mapped[str] = mapped_column(
        String(20), server_default="khac", nullable=False
    )
    mo_ta: Mapped[Optional[str]] = mapped_column(Text)
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    lap_lai: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    # Phase 4 P&L — phân bổ định phí. 1 = ghi nhận đầy đủ trong kỳ thang_bat_dau
    # (hoặc hàng tháng nếu lap_lai). >1 = phân bổ đều cho `so_thang_phan_bo` tháng
    # liên tiếp kể từ thang_bat_dau (vd thuê VP trả 1 lần cho 12 tháng).
    so_thang_phan_bo: Mapped[int] = mapped_column(
        Integer, server_default="1", nullable=False
    )
    # Phase 5C — phương pháp phân bổ chi phí (enum):
    #   duong_thang | prorated_by_day | front_loaded | seasonal | by_revenue_pct | manual
    # Default 'duong_thang' để legacy data không phá vỡ.
    phuong_phap_phan_bo: Mapped[str] = mapped_column(
        String(20), server_default="duong_thang", nullable=False
    )
    # Phase 5C — JSONB tỷ lệ % tháng cho method='manual'.
    # Format: {"01": 10, "02": 5, ..., "12": 15}  (đơn vị %)
    # Hoặc {"YYYY-MM": pct} cho phân bổ cụ thể theo năm-tháng.
    phan_bo_manual: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

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
        return f"<ChiPhiCoDinh {self.id} {self.thang_bat_dau} {self.so_tien_thang}>"
