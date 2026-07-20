"""BOMMaster — header BOM giá vốn (M2).

1 BOM gắn theo nhóm sản phẩm (category_id) — nhiều SP cùng nhóm dùng chung.
Phiên bản BOM = cặp effective_from / effective_to (NULL = vẫn áp dụng).
tong_gia_von cache SUM(items.thanh_tien) — recalc khi item đổi (service bom_calc).
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from shared.db import Base

if TYPE_CHECKING:
    from .bom_item import BOMItem
    from .product_category import InvProductCategory


class BOMMaster(Base):
    __tablename__ = "bom_master"
    __table_args__ = (
        UniqueConstraint("ma_bom", name="uq_bom_master_ma_bom"),
        Index("ix_bom_category", "category_id"),
        Index("ix_bom_active", "active"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ma_bom: Mapped[str] = mapped_column(String(32), nullable=False)
    ten_bom: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ketoan.product_category.id", ondelete="SET NULL"),
        nullable=True,
    )
    effective_from: Mapped[date] = mapped_column(
        Date, server_default=func.current_date(), nullable=False
    )
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    tong_gia_von: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
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

    items: Mapped[list["BOMItem"]] = relationship(
        "BOMItem",
        back_populates="bom",
        cascade="all, delete-orphan",
        order_by="BOMItem.id",
    )
    category: Mapped[Optional["InvProductCategory"]] = relationship(
        "InvProductCategory",
        lazy="joined",
        foreign_keys=[category_id],
    )

    def __repr__(self) -> str:
        return f"<BOMMaster {self.ma_bom} {self.ten_bom!r}>"
