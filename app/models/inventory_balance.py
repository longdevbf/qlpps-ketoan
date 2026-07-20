"""InventoryBalance — tồn cuối kỳ + giá vốn bình quân gia quyền (M1).

1 row / SP. Cập nhật trong cùng transaction với InventoryMovement
(qua service `inventory_avg.apply_movement`).
"""
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from shared.db import Base

if TYPE_CHECKING:
    from .product import InvProduct


class InventoryBalance(Base):
    __tablename__ = "inventory_balance"
    __table_args__ = (
        {"schema": "ketoan"},
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("ketoan.product.id", ondelete="CASCADE"),
        primary_key=True,
    )
    so_luong_ton: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )
    gia_von_bq: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )
    gia_tri_ton: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )
    ton_min: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )
    ton_max: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    product: Mapped["InvProduct"] = relationship(
        "InvProduct",
        back_populates="balance",
    )

    def __repr__(self) -> str:
        return f"<InventoryBalance p={self.product_id} ton={self.so_luong_ton}>"
