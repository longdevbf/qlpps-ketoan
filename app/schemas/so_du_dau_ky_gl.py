"""Pydantic v2 — Số dư đầu kỳ theo hệ thống tài khoản kế toán (GL)."""
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .tam_ung import _vnd


class SoDuTaiKhoanIn(BaseModel):
    # TK loại 1–4; tiền nhập theo TK con (1111, 1121…) — service kiểm theo tai_khoan_co_so_du().
    tk: str = Field(..., max_length=10)
    du_no: Decimal = Field(Decimal("0"), ge=0, max_digits=15)
    du_co: Decimal = Field(Decimal("0"), ge=0, max_digits=15)

    _v_no = field_validator("du_no")(_vnd)
    _v_co = field_validator("du_co")(_vnd)


class SoDuDoiTuongIn(SoDuTaiKhoanIn):
    id: str = Field(..., min_length=1, max_length=64)
    ma: Optional[str] = Field(None, max_length=64)
    ten: Optional[str] = Field(None, max_length=255)


class SoDuDauKyIn(BaseModel):
    """PUT /api/so-du-dau-ky-gl — thay TOÀN BỘ số dư đầu kỳ (dòng không gửi = 0)."""

    tai_khoan: list[SoDuTaiKhoanIn] = Field(default_factory=list, max_length=200)
    doi_tuong: list[SoDuDoiTuongIn] = Field(default_factory=list, max_length=5000)
