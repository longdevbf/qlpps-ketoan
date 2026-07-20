"""Pydantic schemas — TaiKhoanNH."""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TaiKhoanNHBase(BaseModel):
    ten_tk: str
    loai: str = "ngan_hang"           # 'ngan_hang' | 'tien_mat'
    ten_nh: Optional[str] = None
    so_tk: Optional[str] = None
    chu_tk: Optional[str] = None
    chi_nhanh: Optional[str] = None
    so_du_dau: Decimal = Decimal("0")
    mo_ta: Optional[str] = None
    active: bool = True


class TaiKhoanNHCreate(TaiKhoanNHBase):
    pass


class TaiKhoanNHUpdate(BaseModel):
    ten_tk: Optional[str] = None
    loai: Optional[str] = None
    ten_nh: Optional[str] = None
    so_tk: Optional[str] = None
    chu_tk: Optional[str] = None
    chi_nhanh: Optional[str] = None
    so_du_dau: Optional[Decimal] = None
    mo_ta: Optional[str] = None
    active: Optional[bool] = None


class TaiKhoanNHOut(TaiKhoanNHBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
