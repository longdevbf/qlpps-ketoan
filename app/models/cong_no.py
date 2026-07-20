"""CongNo — công nợ phải thu / phải trả (port từ `cong_no.json` + `KT_CongNo` sheet).

V1 fields:
    id ('CN-XXXXXXXX'), loai ('Công Nợ Khách Hàng'/'Công Nợ NCC'/...), doi_tuong, ma_don,
    so_tien, da_tra, con_lai, ngay_phat_sinh, han_thanh_toan, trang_thai ('Còn Nợ'/'Đã Thanh Toán'),
    ghi_chu, ref_id, ref_source, created_by, created_at

V2 chuẩn hoá:
    - id giữ TEXT (không SERIAL) để tương thích migrate
    - loai = 'phai_thu' | 'phai_tra' (chuẩn hoá), loai_chi_tiet giữ raw V1
    - trang_thai = 'chua_tra' | 'da_tra' (chuẩn hoá)
    - con_lai = GENERATED COLUMN (so_tien - da_tra)
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Computed, String, Numeric, DateTime, Date, Text, Index, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class CongNo(Base):
    __tablename__ = "cong_no"
    __table_args__ = (
        Index("ix_cn_ngay", "ngay"),
        Index("ix_cn_loai", "loai"),
        Index("ix_cn_trang_thai", "trang_thai"),
        # uq_cn_ref_id partial — tạo trong migration (op.execute) vì SQLAlchemy không hỗ trợ trực tiếp WHERE clause
        {"schema": "ketoan"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)        # 'CN-2026-0001'
    ngay: Mapped[date] = mapped_column(Date, nullable=False)             # ngay_phat_sinh V1
    doi_tac: Mapped[str] = mapped_column(String(255), nullable=False)    # 'doi_tuong' V1

    so_tien: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )
    da_tra: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )
    con_lai: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        Computed("so_tien - da_tra", persisted=True),
    )

    loai: Mapped[str] = mapped_column(
        String(32), nullable=False
    )                                                                    # 'phai_thu' | 'phai_tra'
    loai_chi_tiet: Mapped[Optional[str]] = mapped_column(String(64))     # raw V1 loai

    ma_don: Mapped[Optional[str]] = mapped_column(String(64))            # ref baogia.quotes.quote_number / muahang.purchase_orders.id
    ref_id: Mapped[Optional[str]] = mapped_column(String(128))           # 'MH-KH-BG2026-0002' dedup
    ref_source: Mapped[Optional[str]] = mapped_column(String(32))        # 'mua_hang' | 'sale_admin' | 'manual'

    han_thanh_toan: Mapped[Optional[str]] = mapped_column(String(64))    # giữ TEXT vì V1 lưu DD/MM/YYYY hoặc note

    trang_thai: Mapped[str] = mapped_column(
        String(32), server_default="chua_tra", nullable=False
    )                                                                    # 'chua_tra' | 'da_tra'
    ngay_tra: Mapped[Optional[date]] = mapped_column(Date)

    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    chung_tu_url: Mapped[Optional[str]] = mapped_column(Text)            # local upload URL `/api/uploads/cong_no_<id>/<file>`

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
        return f"<CongNo {self.id} {self.doi_tac} {self.con_lai} {self.trang_thai}>"
