"""SoDuDauKyDoiTuong — chi tiết số dư đầu kỳ công nợ theo đối tượng (131/331/141).

Số dư đầu kỳ THEO TÀI KHOẢN KẾ TOÁN không lưu bảng riêng: nó là MỘT bút toán
journal `source_type='so_du_dau_ky'` (xem services/so_du_dau_ky_gl.py) để mọi
sổ cái / cân đối phát sinh / cân đối kế toán đọc từ journal tự có số dư nền.
Bảng này chỉ giữ phần chi tiết từng khách hàng / NCC / nhân viên — tổng chi tiết
của một TK phải bằng số dư TK đó (kiểm ở service trước khi lưu).

KHÁC `ketoan.so_du_dau_ky` (models/so_du_dau_ky.py) = số dư đầu tháng của TÀI
KHOẢN NGÂN HÀNG/tiền mặt, dùng cho sổ quỹ — hai khái niệm độc lập.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class SoDuDauKyDoiTuong(Base):
    __tablename__ = "so_du_dau_ky_doi_tuong"
    __table_args__ = (
        UniqueConstraint("tk", "doi_tuong_id", name="uq_sddk_dt_tk_dt"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tk: Mapped[str] = mapped_column(String(10), nullable=False)
    doi_tuong_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ma: Mapped[Optional[str]] = mapped_column(String(64))
    ten: Mapped[str] = mapped_column(String(255), nullable=False)
    du_no: Mapped[Decimal] = mapped_column(Numeric(15, 0), nullable=False, server_default="0")
    du_co: Mapped[Decimal] = mapped_column(Numeric(15, 0), nullable=False, server_default="0")
    updated_by: Mapped[Optional[str]] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )
