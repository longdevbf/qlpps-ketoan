"""Pydantic schemas — Giao dịch Quỹ DN (thu/chi)."""
from datetime import date as date_cls, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


_LOAI_VALID = {"thu", "chi"}
_SOURCE_TYPES_VALID = {
    "manual", "trich_quy", "chi_phi", "hoan_quy", "dieu_chinh", "khac",
}


class QuyDNGiaoDichCreate(BaseModel):
    """Body cho POST /nap và POST /chi.

    `loai` không cần truyền (router tự gán theo endpoint).
    """
    ngay: date_cls
    so_tien: Decimal = Field(gt=0)
    noi_dung: Optional[str] = None
    tai_khoan_id: Optional[int] = None
    ghi_chu: Optional[str] = None
    allow_negative: Optional[bool] = False  # chỉ áp dụng cho /chi


class QuyDNGiaoDichOut(BaseModel):
    id: int
    quy_id: int
    ngay: date_cls
    loai: str
    so_tien: Decimal
    noi_dung: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    tai_khoan_id: Optional[int] = None
    ghi_chu: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("loai")
    @classmethod
    def _check_loai(cls, v: str) -> str:
        if v not in _LOAI_VALID:
            raise ValueError(f"loai phải là 'thu' hoặc 'chi', không phải {v!r}")
        return v
