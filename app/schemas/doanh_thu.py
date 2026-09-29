"""Pydantic schemas — DoanhThu."""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DoanhThuBase(BaseModel):
    ngay: date
    loai: Optional[str] = None
    so_tien: Decimal = Decimal("0")
    nguon: Optional[str] = None
    nv_kinh_doanh: Optional[str] = None
    ma_don: Optional[str] = None
    ref_order_id: Optional[str] = None
    ngan_hang: Optional[str] = None
    loai_thanh_toan: Optional[str] = None
    mo_ta: Optional[str] = None
    ghi_chu: Optional[str] = None


class DoanhThuCreate(DoanhThuBase):
    pass


class DoanhThuUpdate(BaseModel):
    ngay: Optional[date] = None
    loai: Optional[str] = None
    so_tien: Optional[Decimal] = None
    nguon: Optional[str] = None
    nv_kinh_doanh: Optional[str] = None
    ma_don: Optional[str] = None
    ref_order_id: Optional[str] = None
    ngan_hang: Optional[str] = None
    loai_thanh_toan: Optional[str] = None
    mo_ta: Optional[str] = None
    ghi_chu: Optional[str] = None


class DoanhThuOut(DoanhThuBase):
    id: int
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Phân loại nguồn: nhãn luồng tự động (vd 'Đối chiếu giao hàng') hoặc None = KT tự nhập.
    nguon_hien: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
