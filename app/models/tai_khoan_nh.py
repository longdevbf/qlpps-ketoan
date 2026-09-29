"""TaiKhoanNH — tài khoản ngân hàng / tiền mặt (port từ `tai_khoan_nh.json`)."""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Boolean, Integer, Numeric, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class TaiKhoanNH(Base):
    __tablename__ = "tai_khoan_nh"
    __table_args__ = ({"schema": "ketoan"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ten_tk: Mapped[str] = mapped_column(String(255), nullable=False)         # 'BIDV Công Ty', 'Tiền Mặt'
    loai: Mapped[str] = mapped_column(
        String(32), server_default="ngan_hang", nullable=False
    )                                                                         # 'ngan_hang' | 'tien_mat'
    ten_nh: Mapped[Optional[str]] = mapped_column(String(128))                # 'BIDV', 'ACB',...
    so_tk: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    chu_tk: Mapped[Optional[str]] = mapped_column(String(255))
    chi_nhanh: Mapped[Optional[str]] = mapped_column(String(255))
    so_du_dau: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )
    mo_ta: Mapped[Optional[str]] = mapped_column(Text)
    # TK kế toán con của 111/112 (1111, 1121…) — cột thêm 28/09/2026 bởi services/tai_khoan_tien.py (lifespan)
    tk_ke_toan: Mapped[Optional[str]] = mapped_column(String(10), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)

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
        return f"<TaiKhoanNH {self.id} {self.ten_tk!r}>"
