"""BOMItem — chi tiết NVL trong BOM (M2).

thanh_tien là cột GENERATED ALWAYS AS (so_luong * don_gia) STORED ở DB
(xem migration m2bom_2026_04_28_bom). Ở Python coi như read-only.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Computed, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from shared.db import Base

if TYPE_CHECKING:
    from .bom_master import BOMMaster


class BOMItem(Base):
    __tablename__ = "bom_item"
    __table_args__ = (
        Index("ix_bom_item_bom", "bom_id"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bom_id: Mapped[int] = mapped_column(
        ForeignKey("ketoan.bom_master.id", ondelete="CASCADE"),
        nullable=False,
    )
    ten_nvl: Mapped[str] = mapped_column(String(255), nullable=False)
    dvt: Mapped[Optional[str]] = mapped_column(String(32))
    so_luong: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    don_gia: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    thanh_tien: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        Computed("so_luong * don_gia", persisted=True),
        nullable=False,
    )
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    bom: Mapped["BOMMaster"] = relationship(
        "BOMMaster", back_populates="items"
    )

    def __repr__(self) -> str:
        return f"<BOMItem {self.id} bom={self.bom_id} {self.ten_nvl!r} sl={self.so_luong}>"
