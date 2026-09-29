"""ThueTndnDieuChinh — khoản điều chỉnh thu nhập tính thuế TNDN tạm tính theo quý.

Màn /ketoan/thue-tncn-tndn (tab TNDN): lợi nhuận kế toán lấy từ báo cáo KQKD
(`services/pl_calculator.py:calc_pl_for_month`), kế toán tự khai các khoản
chi phí không được trừ (tăng) / thu nhập không chịu thuế, lỗ chuyển (giảm).
Mỗi lần lưu thay toàn bộ các dòng của quý (all-or-nothing).

Bảng tạo bằng DDL idempotent trong `services/thue_phan_bo_schema.py`
(không dùng alembic — cùng cách các bảng ketoan mới từ 2026-06).
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class ThueTndnDieuChinh(Base):
    __tablename__ = "thue_tndn_dieu_chinh"
    __table_args__ = ({"schema": "ketoan"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quy: Mapped[str] = mapped_column(String(8), nullable=False)          # 'Q3-2026'
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    loai: Mapped[str] = mapped_column(String(4), nullable=False)          # 'tang' | 'giam'
    noi_dung: Mapped[str] = mapped_column(String(200), nullable=False)
    so_tien: Mapped[Decimal] = mapped_column(Numeric(15, 0), nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
