"""ProductAttribute — danh mục thuộc tính theo nhóm master sản phẩm.

Quản lý ở app Kế Toán (master data), các app khác (báo giá / mua hàng /
marketing / saleadmin) READ để render dropdown khi thêm/sửa SP.

Vai trò:
- 1 nhóm master ('Đồ Gỗ' / 'Đồ Mây' / 'Dự Án' …) có nhiều attr_key
  ("Màu gỗ", "Vân gỗ", "Loại nan mây", "Kích thước"…).
- 1 attr_key có nhiều attr_value ("Walnut", "Oak", "Teak"…).

Bảng flat (1 row = 1 (nhom_master, attr_key, attr_value)) — gọn, dễ
upsert per-row khi user CRUD; FE group lại theo (nhom_master, attr_key).
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, DateTime, Index, Integer, Numeric, String,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class ProductAttribute(Base):
    __tablename__ = "product_attributes"
    # UniqueConstraint cũ thay bằng partial unique indexes (xem migration
    # 0008): default per nhom (product_id IS NULL) vs per-product
    # (product_id IS NOT NULL). SQLAlchemy không hỗ trợ partial unique
    # khai báo trực tiếp trong __table_args__, nên không reflect ở đây.
    __table_args__ = (
        Index(
            "ix_product_attributes_nhom_key",
            "nhom_master", "attr_key",
        ),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nhom_master: Mapped[str] = mapped_column(String(64), nullable=False)
    # product_id NULL = default cả nhom; non-NULL = override riêng cho 1 SP
    product_id: Mapped[int | None] = mapped_column(Integer)
    attr_key: Mapped[str] = mapped_column(String(64), nullable=False)
    attr_value: Mapped[str] = mapped_column(String(255), nullable=False)
    coeff: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    thu_tu: Mapped[int] = mapped_column(
        Integer, server_default="0", nullable=False
    )
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

    def __repr__(self) -> str:
        return (
            f"<ProductAttribute {self.nhom_master}/{self.attr_key}"
            f"={self.attr_value!r}>"
        )
