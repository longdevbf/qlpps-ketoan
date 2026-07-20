"""InvProduct — sản phẩm trong module Tồn Kho (M1).

KHÁC với `shared.products.Product` — đó là master catalog cross-app
(báo giá / mua hàng / marketing dùng chung). InvProduct là bản
inventory-focused riêng cho module Tồn Kho:
  - Tham chiếu cây danh mục `ketoan.product_category`
  - Lưu attributes JSONB (màu/size variants — theo quy ước Papasan,
    1 SP = 1 SKU, không tách kho theo màu/size)
  - Bom_id NULL (M2 sẽ thêm bảng bom_master)
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional, TYPE_CHECKING

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from shared.db import Base

if TYPE_CHECKING:
    from .product_category import InvProductCategory
    from .inventory_balance import InventoryBalance


class InvProduct(Base):
    __tablename__ = "product"
    __table_args__ = (
        UniqueConstraint("ma_sp", name="uq_inv_product_ma_sp"),
        Index("ix_inv_product_category", "category_id"),
        Index("ix_inv_product_active", "active"),
        Index("ix_inv_product_ten_sp", "ten_sp"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ma_sp: Mapped[str] = mapped_column(String(64), nullable=False)
    ten_sp: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("ketoan.product_category.id", ondelete="RESTRICT"),
        nullable=False,
    )
    dvt: Mapped[str] = mapped_column(
        String(32), server_default="cái", nullable=False
    )
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, server_default="{}"
    )
    gia_ban_mac_dinh: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )
    bom_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hinh_anh: Mapped[Optional[str]] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    category: Mapped["InvProductCategory"] = relationship(
        "InvProductCategory",
        back_populates="products",
        lazy="joined",
    )
    balance: Mapped[Optional["InventoryBalance"]] = relationship(
        "InventoryBalance",
        back_populates="product",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<InvProduct {self.ma_sp} {self.ten_sp!r}>"
