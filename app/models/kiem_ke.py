"""KiemKe — phiếu kiểm kê tồn (M1).

Khi POST → tự sinh InventoryMovement(loai='dieu_chinh') để cân tồn sổ sách
về tồn thực tế. chenh_lech = ton_thuc_te - ton_so_sach.
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


class KiemKe(Base):
    __tablename__ = "kiem_ke"
    __table_args__ = (
        Index("ix_kk_ngay", "ngay"),
        Index("ix_kk_product", "product_id"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ngay: Mapped[date] = mapped_column(Date, nullable=False)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("ketoan.product.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ton_so_sach: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    ton_thuc_te: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    chenh_lech: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    product: Mapped["InvProduct"] = relationship(  # type: ignore[name-defined]
        "InvProduct", lazy="joined"
    )

    def __repr__(self) -> str:
        return f"<KiemKe {self.id} {self.ngay} p={self.product_id} cl={self.chenh_lech}>"
