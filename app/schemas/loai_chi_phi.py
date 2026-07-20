"""Pydantic schemas — LoaiChiPhi."""
from typing import Optional

from pydantic import BaseModel, ConfigDict


class LoaiChiPhiBase(BaseModel):
    ten: str
    mo_ta: Optional[str] = None
    active: bool = True
    nhom_default: Optional[str] = "khac"  # ban_hang | quan_ly | tai_chinh | khac


class LoaiChiPhiCreate(LoaiChiPhiBase):
    pass


class LoaiChiPhiUpdate(BaseModel):
    ten: Optional[str] = None
    mo_ta: Optional[str] = None
    active: Optional[bool] = None
    nhom_default: Optional[str] = None


class LoaiChiPhiOut(LoaiChiPhiBase):
    id: int
    model_config = ConfigDict(from_attributes=True)
