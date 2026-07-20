"""ProductCategory — cây danh mục SP phân cấp (M1 inventory).

Khác với `shared.products.nhom_hang` (master catalog cross-app, đơn giản),
đây là cây phân cấp riêng cho module Tồn Kho của Kế Toán — cho phép
rollup giá trị tồn theo nhóm/nhánh.
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from shared.db import Base

if TYPE_CHECKING:
    from .product import InvProduct


class InvProductCategory(Base):
    __tablename__ = "product_category"
    __table_args__ = (
        UniqueConstraint("ma_nhom", name="uq_product_category_ma_nhom"),
        Index("ix_pc_parent", "parent_id"),
        Index("ix_pc_active", "active"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ma_nhom: Mapped[str] = mapped_column(String(32), nullable=False)
    ten_nhom: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ketoan.product_category.id", ondelete="SET NULL"),
        nullable=True,
    )
    display_order: Mapped[int] = mapped_column(
        Integer, server_default="0", nullable=False
    )
    active: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    parent: Mapped[Optional["InvProductCategory"]] = relationship(
        "InvProductCategory",
        remote_side="InvProductCategory.id",
        back_populates="children",
    )
    children: Mapped[list["InvProductCategory"]] = relationship(
        "InvProductCategory",
        back_populates="parent",
        cascade="all",
        order_by="InvProductCategory.display_order, InvProductCategory.id",
    )
    products: Mapped[list["InvProduct"]] = relationship(
        "InvProduct",
        back_populates="category",
        cascade="all",
    )

    def __repr__(self) -> str:
        return f"<InvProductCategory {self.ma_nhom} {self.ten_nhom!r}>"
