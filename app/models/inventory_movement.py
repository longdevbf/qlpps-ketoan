"""InventoryMovement — sổ chi tiết nhập/xuất/điều chỉnh tồn kho (M1).

loai ∈ {nhap, xuat, dieu_chinh}
- nhap: từ PO mua hàng (bridge muahang) hoặc manual
- xuat: từ VC giao khách (bridge saleadmin) hoặc manual
- dieu_chinh: kiểm kê — số lượng có thể âm

Bình quân gia quyền (xem `services.inventory_avg`):
- nhap → recalc avg
- xuat → don_gia OUT = current avg (auto override input)
- dieu_chinh → giá vốn không đổi, chỉ chỉnh số lượng
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from shared.db import Base


class InventoryMovement(Base):
    __tablename__ = "inventory_movement"
    __table_args__ = (
        Index("ix_im_product_ngay", "product_id", "ngay"),
        Index("ix_im_loai", "loai"),
        Index("ix_im_source", "source_app", "source_doc_id"),
        Index("ix_im_ngay", "ngay"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ngay: Mapped[date] = mapped_column(Date, nullable=False)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("ketoan.product.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # nhap | xuat | dieu_chinh
    loai: Mapped[str] = mapped_column(String(20), nullable=False)
    so_luong: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    don_gia: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    thanh_tien: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    source_app: Mapped[Optional[str]] = mapped_column(String(32))   # 'muahang' | 'saleadmin' | 'manual' | 'kiem_ke'
    source_doc_id: Mapped[Optional[str]] = mapped_column(String(64))  # PO id / VC ma_vh / ...
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    product: Mapped["InvProduct"] = relationship(  # type: ignore[name-defined]
        "InvProduct", lazy="joined"
    )

    def __repr__(self) -> str:
        return f"<InventoryMovement {self.id} {self.loai} p={self.product_id} sl={self.so_luong}>"
