"""Product + ProductAddon — master catalog dùng chung mọi app.

Ketoan: CRUD master data.
Baogia: đọc để render dropdown form báo giá + tính giá.
Marketing: đọc để chạy ads (hinh_anh, mo_ta).
Saleadmin (kinh doanh): đọc để lên đơn (ten_sp, gia_co_ban).
Muahang: đọc để đặt hàng NCC (ten_sp, gia_von, nhom_hang).

Fields:
- ma_sp UNIQUE (slug ổn định, không đổi khi rename ten_sp)
- ten_sp / label / dvt
- unit ∈ {met_dai, met_vuong, size_table, fixed} — cách tính giá báo giá
- gia_co_ban — giá bán cơ bản
- gia_von — giá vốn (cho mua hàng + kế toán)
- dimensions / dim_labels / sizes — input form báo giá
- hinh_anh — URL/path ảnh đại diện (cho marketing chạy ads)
- mo_ta — mô tả dài (cho marketing + saleadmin)
- nhom_hang — phân loại (Giường / Sofa / Bàn / ...) cho mua hàng
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from shared.db import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("ma_sp", name="uq_products_ma_sp"),
        Index("ix_products_ten_sp", "ten_sp"),
        Index("ix_products_active", "active"),
        Index("ix_products_nhom_hang", "nhom_hang"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ma_sp: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    ten_sp: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(255))
    dvt: Mapped[Optional[str]] = mapped_column(String(32))
    unit: Mapped[Optional[str]] = mapped_column(String(32))  # met_dai|met_vuong|size_table|fixed
    nhom_hang: Mapped[Optional[str]] = mapped_column(String(64))
    # Phase 6A — Nhóm Master (cho phân bổ CPA Ads): 'Đồ Gỗ' | 'Đồ Mây' | 'Dự Án' | NULL
    # NULL = chưa phân loại; pool ads gắn nhóm này gộp vào "Khác" và chia đều 3 nhóm.
    nhom_master: Mapped[Optional[str]] = mapped_column(String(32))
    gia_co_ban: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )
    # Giá sàn — khi báo giá tính ra < gia_min thì dùng gia_min làm minimum
    # charge (vd 10tr/m × 0.5m = 5tr nhưng gia_min=10tr → final 10tr).
    # NULL/0 = không áp dụng sàn.
    gia_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    gia_von: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    dimensions: Mapped[Optional[list]] = mapped_column(JSON)
    dim_labels: Mapped[Optional[list]] = mapped_column(JSON)
    sizes: Mapped[Optional[dict]] = mapped_column(JSON)
    # Giá trị thuộc tính SP đã chọn từ shared.product_attributes
    # VD: {"Màu gỗ": "Walnut", "Vân gỗ": "Vân thẳng", "Kích thước": "100x200"}
    attributes: Mapped[Optional[dict]] = mapped_column(
        JSONB, server_default="{}"
    )
    kich_thuoc_chuan: Mapped[Optional[str]] = mapped_column(String(255))
    mau_chuan: Mapped[Optional[str]] = mapped_column(String(128))
    hinh_anh: Mapped[Optional[str]] = mapped_column(String(512))
    mo_ta: Mapped[Optional[str]] = mapped_column(Text)
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    thu_tu: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    addons: Mapped[list["ProductAddon"]] = relationship(
        "ProductAddon",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductAddon.thu_tu",
    )

    def __repr__(self) -> str:
        return f"<Product {self.ma_sp} {self.ten_sp!r}>"


class ProductAddon(Base):
    __tablename__ = "product_addons"
    __table_args__ = (
        UniqueConstraint("product_id", "ten_addon", name="uq_product_addon"),
        Index("ix_product_addons_product", "product_id"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("shared.products.id", ondelete="CASCADE"), nullable=False
    )
    ten_addon: Mapped[str] = mapped_column(String(255), nullable=False)
    gia_addon: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )
    dvt: Mapped[Optional[str]] = mapped_column(String(32))
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    thu_tu: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    # Legacy flag (giữ cho backward compat, sẽ drop). True = per_m2.
    tinh_per_m2: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    # Mode tính addon: 'flat' (cộng thẳng) | 'per_m2' (× R × C) | 'per_m_dai' (× R)
    cach_tinh: Mapped[str] = mapped_column(
        String(16), server_default="flat", nullable=False
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

    product: Mapped["Product"] = relationship("Product", back_populates="addons")

    def __repr__(self) -> str:
        return f"<ProductAddon p={self.product_id} {self.ten_addon!r}>"
