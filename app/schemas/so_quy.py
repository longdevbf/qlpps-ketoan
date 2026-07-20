"""Pydantic schemas — SoQuy."""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# Enum cho phân loại dòng tiền (TT200) — UI dropdown
PHAN_LOAI_CF_VALUES = (
    "thu_kh", "tra_ncc", "nap_ads", "tra_luong",
    "mua_ccdc", "sua_chua_lon", "vay_nh", "tra_nh", "khac",
)
_PCF_PATTERN = "^(" + "|".join(PHAN_LOAI_CF_VALUES) + ")$"


class SoQuyBase(BaseModel):
    ngay: date
    loai: str = Field(..., pattern="^(thu|chi)$")
    so_tien: Decimal = Decimal("0")
    tai_khoan: Optional[str] = None
    noi_dung: Optional[str] = None
    lien_quan: Optional[str] = None
    phan_loai_cf: Optional[str] = Field(default=None, pattern=_PCF_PATTERN)
    ref_id: Optional[str] = None
    ref_vc: Optional[str] = None
    mo_ta: Optional[str] = None
    ghi_chu: Optional[str] = None
    nhan_vien_id: Optional[int] = None
    nhan_vien_ten: Optional[str] = None
    # Anh Quang 2026-06-06: Mã đơn báo giá liên kết (multi-cọc)
    ma_don: Optional[str] = None


class SoQuyCreate(SoQuyBase):
    pass


class SoQuyUpdate(BaseModel):
    ngay: Optional[date] = None
    loai: Optional[str] = Field(default=None, pattern="^(thu|chi)$")
    so_tien: Optional[Decimal] = None
    tai_khoan: Optional[str] = None
    noi_dung: Optional[str] = None
    lien_quan: Optional[str] = None
    phan_loai_cf: Optional[str] = Field(default=None, pattern=_PCF_PATTERN)
    ref_id: Optional[str] = None
    mo_ta: Optional[str] = None
    ghi_chu: Optional[str] = None
    nhan_vien_id: Optional[int] = None
    nhan_vien_ten: Optional[str] = None
    ma_don: Optional[str] = None


class SoQuyOut(SoQuyBase):
    id: int
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
