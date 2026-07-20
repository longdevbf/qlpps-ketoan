"""Pydantic schemas — Product + ProductAddon (master catalog).

Chỉ Kế Toán dùng các schema Create/Update này (CRUD). Các app khác chỉ đọc
qua `ProductOut`.
"""
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ────────────────────────── Addon ──────────────────────────────────────

class ProductAddonBase(BaseModel):
    ten_addon: str
    gia_addon: Decimal = Decimal("0")
    dvt: Optional[str] = None
    ghi_chu: Optional[str] = None
    thu_tu: int = 0
    # Mode tính: 'flat' | 'per_m2' | 'per_m_dai'
    cach_tinh: str = "flat"
    # Legacy flag (giữ cho backward compat với client cũ)
    tinh_per_m2: bool = False


class ProductAddonCreate(ProductAddonBase):
    pass


class ProductAddonUpdate(BaseModel):
    ten_addon: Optional[str] = None
    gia_addon: Optional[Decimal] = None
    dvt: Optional[str] = None
    ghi_chu: Optional[str] = None
    thu_tu: Optional[int] = None
    cach_tinh: Optional[str] = None
    tinh_per_m2: Optional[bool] = None


class ProductAddonOut(ProductAddonBase):
    id: int
    product_id: int
    model_config = ConfigDict(from_attributes=True)


# ────────────────────────── Product ────────────────────────────────────

class ProductBase(BaseModel):
    ma_sp: str = Field(..., max_length=64)
    ten_sp: str = Field(..., max_length=255)
    label: Optional[str] = None
    dvt: Optional[str] = None
    unit: Optional[str] = Field(
        None, description="met_dai | met_vuong | size_table | fixed"
    )
    nhom_hang: Optional[str] = None
    nhom_master: Optional[str] = Field(
        None, description="Đồ Gỗ | Đồ Mây | Dự Án | NULL (cho phân bổ CPA Ads)"
    )
    gia_co_ban: Decimal = Decimal("0")
    # Giá sàn (minimum charge) — báo giá tính ra < gia_min thì dùng gia_min
    gia_min: Optional[Decimal] = None
    gia_von: Optional[Decimal] = None
    dimensions: Optional[list[Any]] = None
    dim_labels: Optional[list[Any]] = None
    sizes: Optional[dict[str, Any]] = None
    attributes: Optional[dict[str, Any]] = None
    kich_thuoc_chuan: Optional[str] = None
    mau_chuan: Optional[str] = None
    hinh_anh: Optional[str] = None
    mo_ta: Optional[str] = None
    ghi_chu: Optional[str] = None
    active: bool = True
    thu_tu: int = 0


class ProductCreate(ProductBase):
    addons: list[ProductAddonCreate] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    ma_sp: Optional[str] = None
    ten_sp: Optional[str] = None
    label: Optional[str] = None
    dvt: Optional[str] = None
    unit: Optional[str] = None
    nhom_hang: Optional[str] = None
    nhom_master: Optional[str] = None
    gia_co_ban: Optional[Decimal] = None
    gia_min: Optional[Decimal] = None
    gia_von: Optional[Decimal] = None
    dimensions: Optional[list[Any]] = None
    dim_labels: Optional[list[Any]] = None
    sizes: Optional[dict[str, Any]] = None
    attributes: Optional[dict[str, Any]] = None
    kich_thuoc_chuan: Optional[str] = None
    mau_chuan: Optional[str] = None
    hinh_anh: Optional[str] = None
    mo_ta: Optional[str] = None
    ghi_chu: Optional[str] = None
    active: Optional[bool] = None
    thu_tu: Optional[int] = None


class ProductOut(ProductBase):
    id: int
    addons: list[ProductAddonOut] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)
