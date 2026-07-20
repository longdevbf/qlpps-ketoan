"""Pydantic schemas — SoDuDauKy."""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SoDuDauKyBase(BaseModel):
    thang: date                                    # yyyy-mm-01 (FE phải truyền dạng date)
    tai_khoan_id: Optional[int] = None
    so_du: Decimal = Decimal("0")
    ghi_chu: Optional[str] = None


class SoDuDauKyCreate(SoDuDauKyBase):
    pass


class SoDuDauKyOut(SoDuDauKyBase):
    id: int
    created_at: datetime
    # join field optional — populated từ router khi join tai_khoan_nh
    ten_tk: Optional[str] = None
    loai_tk: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
