"""DonVi — thông tin đơn vị kế toán in trên chứng từ/báo cáo (letterhead).

Bảng singleton: đúng 1 dòng, id=1 (CHECK constraint). Đọc qua GET /api/don-vi
(dùng cho trang in `/ketoan/in`) + GET /api/cai-dat (tab "Đơn vị" màn Cài đặt),
sửa qua PUT /api/cai-dat/don_vi — chỉ CEO/admin/trợ lý CEO (anh Quang 2026-09-25).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class DonVi(Base):
    __tablename__ = "don_vi"
    __table_args__ = (
        CheckConstraint("id = 1", name="don_vi_singleton_ck"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    ten: Mapped[str] = mapped_column(String(200), nullable=False, server_default="")
    ten_ngan: Mapped[Optional[str]] = mapped_column(String(40))
    mst: Mapped[Optional[str]] = mapped_column(String(14))
    dien_thoai: Mapped[Optional[str]] = mapped_column(String(20))
    dia_chi: Mapped[Optional[str]] = mapped_column(String(240))
    email: Mapped[Optional[str]] = mapped_column(String(120))
    giam_doc: Mapped[Optional[str]] = mapped_column(String(80))
    ke_toan_truong: Mapped[Optional[str]] = mapped_column(String(80))
    thu_quy: Mapped[Optional[str]] = mapped_column(String(80))
    updated_by: Mapped[Optional[str]] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<DonVi {self.ten!r} mst={self.mst}>"
