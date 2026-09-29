"""Pydantic v2 — Tạm ứng nhân viên (TK 141)."""
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


def _vnd(v: Decimal) -> Decimal:
    """Tiền VND là số nguyên — không nhận phần lẻ."""
    if v != v.to_integral_value():
        raise ValueError("Số tiền VND phải là số nguyên")
    return v


class TamUngIn(BaseModel):
    """POST /api/tam-ung · PUT /api/tam-ung/{id}"""

    nhan_vien_ma: str = Field(..., min_length=1, max_length=16)
    ngay: date
    so_tien: Decimal = Field(..., gt=0, max_digits=15)
    tai_khoan_id: int
    han_hoan: Optional[date] = None
    noi_dung: str = Field(..., min_length=1, max_length=500)

    _v_tien = field_validator("so_tien")(_vnd)

    @field_validator("noi_dung")
    @classmethod
    def _khong_rong(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Nội dung tạm ứng không được để trống")
        return v


class QuyetToanIn(BaseModel):
    """POST /api/tam-ung/quyet-toan (hợp đồng dữ liệu của kt-tam-ung.js)."""

    id: int
    chi_phi: Decimal = Field(Decimal("0"), ge=0, max_digits=15)
    tk_cp: Optional[str] = Field(None, max_length=10)
    het: bool = True
    xu_ly_thua: str = "thu_tien"
    ngay: date
    ghi_chu: Optional[str] = Field(None, max_length=120)

    _v_tien = field_validator("chi_phi")(_vnd)
