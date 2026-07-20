"""Pydantic schemas — BOM Giá Vốn (M2).

Header (BOMMaster) + items (BOMItem) nested. Margin report so giá vốn
BOM (lý thuyết) vs giá bán bình quân thực tế (theo nhóm SP).
"""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ─────────── BOMItem ───────────

class BOMItemIn(BaseModel):
    ten_nvl: str = Field(..., max_length=255)
    dvt: Optional[str] = Field(default=None, max_length=32)
    so_luong: Decimal = Field(..., gt=0)
    don_gia: Decimal = Field(..., gt=0)
    ghi_chu: Optional[str] = None


class BOMItemOut(BaseModel):
    id: int
    bom_id: int
    ten_nvl: str
    dvt: Optional[str] = None
    so_luong: Decimal
    don_gia: Decimal
    thanh_tien: Decimal
    ghi_chu: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ─────────── BOMMaster ───────────

class BOMMasterCreate(BaseModel):
    ma_bom: Optional[str] = Field(default=None, max_length=32)  # auto-gen nếu trống
    ten_bom: str = Field(..., max_length=255)
    category_id: int
    effective_from: Optional[date] = None  # default = today
    effective_to: Optional[date] = None
    ghi_chu: Optional[str] = None
    items: List[BOMItemIn] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _check_dates(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to phải >= effective_from")
        return self


class BOMMasterUpdate(BaseModel):
    ma_bom: Optional[str] = Field(default=None, max_length=32)
    ten_bom: Optional[str] = Field(default=None, max_length=255)
    category_id: Optional[int] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    ghi_chu: Optional[str] = None
    active: Optional[bool] = None
    # PUT: nếu items được gửi → full-replace (xoá hết + insert mới).
    items: Optional[List[BOMItemIn]] = None

    @field_validator("items")
    @classmethod
    def _check_items_nonempty(cls, v):
        if v is not None and len(v) == 0:
            raise ValueError("items không được rỗng (PUT replace items)")
        return v


class BOMMasterOut(BaseModel):
    id: int
    ma_bom: str
    ten_bom: str
    category_id: Optional[int] = None
    ten_nhom: Optional[str] = None  # enrich
    effective_from: date
    effective_to: Optional[date] = None
    tong_gia_von: Decimal
    ghi_chu: Optional[str] = None
    active: bool
    created_at: datetime
    updated_at: datetime
    items: List[BOMItemOut] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class BOMMasterListOut(BaseModel):
    """Bản gọn cho list view (không kèm items)."""
    id: int
    ma_bom: str
    ten_bom: str
    category_id: Optional[int] = None
    ten_nhom: Optional[str] = None
    effective_from: date
    effective_to: Optional[date] = None
    tong_gia_von: Decimal
    active: bool
    so_items: int = 0
    model_config = ConfigDict(from_attributes=True)


# ─────────── Margin report ───────────

class BOMMarginReportOut(BaseModel):
    category_id: int
    ma_nhom: Optional[str] = None
    ten_nhom: str
    bom_id: Optional[int] = None
    ma_bom: Optional[str] = None
    bom_gia_von: Decimal = Decimal("0")
    gia_ban_bq: Decimal = Decimal("0")
    margin_pct: Optional[Decimal] = None  # NULL nếu gia_ban_bq = 0
    so_luong_xuat: Decimal = Decimal("0")
    doanh_thu_thuc: Decimal = Decimal("0")
