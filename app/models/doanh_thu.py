"""DoanhThu — phiếu thu doanh số (port từ `KT_DoanhThu` sheet + V1 doanh_thu.json)."""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Numeric, DateTime, Date, Integer, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class DoanhThu(Base):
    __tablename__ = "doanh_thu"
    __table_args__ = (
        Index("ix_doanh_thu_ngay", "ngay"),
        Index("ix_doanh_thu_loai", "loai"),
        Index("ix_doanh_thu_nv", "nv_kinh_doanh"),
        Index("ix_doanh_thu_ref_order", "ref_order_id"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ngay: Mapped[date] = mapped_column(Date, nullable=False)
    loai: Mapped[Optional[str]] = mapped_column(String(64))           # 'Doanh Số Đồ Gỗ Lẻ',...
    so_tien: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )
    nguon: Mapped[Optional[str]] = mapped_column(String(32))           # 'kd' | 'online' | 'khac'
    nv_kinh_doanh: Mapped[Optional[str]] = mapped_column(String(128))
    ma_don: Mapped[Optional[str]] = mapped_column(String(64))          # ref baogia.quotes.quote_number (loose)
    # ref muahang.purchase_orders.id — NULL nếu không từ PO. Partial UNIQUE ở DB
    # để đảm bảo 1 PO chỉ ghi 1 entry doanh thu (idempotent auto-create).
    ref_order_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    ngan_hang: Mapped[Optional[str]] = mapped_column(String(128))      # ref ketoan.tai_khoan_nh.ten_tk (loose)
    loai_thanh_toan: Mapped[Optional[str]] = mapped_column(String(32)) # 'Đặt Cọc' | 'Thanh Toán' | 'Hoàn Tiền'
    mo_ta: Mapped[Optional[str]] = mapped_column(Text)
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    chung_tu_url: Mapped[Optional[str]] = mapped_column(Text)         # local upload URL `/api/uploads/doanh_thu_<id>/<file>`

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
        return f"<DoanhThu {self.id} {self.ngay} {self.so_tien}>"
