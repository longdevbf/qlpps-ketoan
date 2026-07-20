"""Pydantic schemas — InvProduct + InventoryBalance + InventoryMovement + KiemKe."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional, List

from pydantic import BaseModel, ConfigDict, Field


# ─────────── InvProduct ───────────

class InvProductBase(BaseModel):
    ma_sp: str = Field(..., max_length=64)
    ten_sp: str = Field(..., max_length=255)
    category_id: int
    dvt: str = "cái"
    attributes: Optional[dict[str, Any]] = Field(default_factory=dict)
    gia_ban_mac_dinh: Decimal = Decimal("0")
    bom_id: Optional[int] = None
    hinh_anh: Optional[str] = None
    active: bool = True


class InvProductCreate(InvProductBase):
    pass


class InvProductUpdate(BaseModel):
    ma_sp: Optional[str] = None
    ten_sp: Optional[str] = None
    category_id: Optional[int] = None
    dvt: Optional[str] = None
    attributes: Optional[dict[str, Any]] = None
    gia_ban_mac_dinh: Optional[Decimal] = None
    bom_id: Optional[int] = None
    hinh_anh: Optional[str] = None
    active: Optional[bool] = None


class InvProductOut(InvProductBase):
    id: int
    created_at: datetime
    updated_at: datetime
    # Issue 4 — enrich từ inventory_balance LEFT JOIN
    so_luong_ton: Optional[Decimal] = Decimal("0")
    gia_von_bq: Optional[Decimal] = Decimal("0")
    model_config = ConfigDict(from_attributes=True)


class InvProductPage(BaseModel):
    total: int
    page: int
    size: int
    items: List[InvProductOut]


# ─────────── InventoryBalance ───────────

class InventoryBalanceOut(BaseModel):
    product_id: int
    so_luong_ton: Decimal
    gia_von_bq: Decimal
    gia_tri_ton: Decimal
    ton_min: Decimal
    ton_max: Decimal
    last_updated: datetime
    # Enrich
    ma_sp: Optional[str] = None
    ten_sp: Optional[str] = None
    dvt: Optional[str] = None
    category_id: Optional[int] = None
    ten_nhom: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class InventoryBalanceTreeNode(BaseModel):
    """Rollup theo cây nhóm — count + value tổng."""
    category_id: Optional[int] = None
    ma_nhom: Optional[str] = None
    ten_nhom: str
    so_sp: int = 0
    tong_sl: Decimal = Decimal("0")
    tong_gia_tri: Decimal = Decimal("0")
    children: List["InventoryBalanceTreeNode"] = Field(default_factory=list)
    products: List[InventoryBalanceOut] = Field(default_factory=list)


InventoryBalanceTreeNode.model_rebuild()


# ─────────── InventoryMovement ───────────

class InventoryMovementBase(BaseModel):
    ngay: date
    product_id: int
    loai: str = Field(..., description="nhap | xuat | dieu_chinh")
    so_luong: Decimal
    don_gia: Decimal = Decimal("0")
    ghi_chu: Optional[str] = None
    source_app: Optional[str] = "manual"
    source_doc_id: Optional[str] = None


class InventoryMovementCreate(InventoryMovementBase):
    """Phase 2 — chỉ áp dụng khi loai='nhap':
      - tai_khoan_id  → Nợ 156 / Có 112 + insert tknhgd 'chi'
      - cong_no_ncc_id → Nợ 156 / Có 331 (không trừ tiền)
    Loai='xuat' / 'dieu_chinh' KHÔNG sinh journal ở đây (xuất kho lấy từ
    bridge bán hàng → tránh trùng).
    """
    tai_khoan_id: Optional[int] = None
    cong_no_ncc_id: Optional[str] = None


class InventoryMovementOut(InventoryMovementBase):
    id: int
    thanh_tien: Decimal
    created_by: Optional[str] = None
    created_at: datetime
    ma_sp: Optional[str] = None
    ten_sp: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# ─────────── KiemKe ───────────

class KiemKeCreate(BaseModel):
    ngay: date
    product_id: int
    ton_thuc_te: Decimal
    ghi_chu: Optional[str] = None


class KiemKeOut(BaseModel):
    id: int
    ngay: date
    product_id: int
    ton_so_sach: Optional[Decimal] = None
    ton_thuc_te: Optional[Decimal] = None
    chenh_lech: Optional[Decimal] = None
    ghi_chu: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    movement_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


# ─────────── Cảnh báo tồn ───────────

class TonKhoCanhBaoOut(BaseModel):
    product_id: int
    ma_sp: str
    ten_sp: str
    so_luong_ton: Decimal
    ton_min: Decimal
    ton_max: Decimal
    loai_canh_bao: str  # 'duoi_min' | 'tren_max'
    model_config = ConfigDict(from_attributes=True)
