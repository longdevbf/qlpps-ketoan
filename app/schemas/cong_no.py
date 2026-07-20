"""Pydantic schemas — CongNo + body cập nhật trả nợ."""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CongNoBase(BaseModel):
    ngay: date
    doi_tac: str
    so_tien: Decimal = Decimal("0")
    da_tra: Decimal = Decimal("0")
    loai: str = Field(..., pattern="^(phai_thu|phai_tra)$")
    loai_chi_tiet: Optional[str] = None
    ma_don: Optional[str] = None
    ref_id: Optional[str] = None
    ref_source: Optional[str] = None
    han_thanh_toan: Optional[str] = None
    trang_thai: str = Field(default="chua_tra", pattern="^(chua_tra|da_tra)$")
    ngay_tra: Optional[date] = None
    ghi_chu: Optional[str] = None
    tai_khoan: Optional[str] = None  # Tài khoản chi/thu khi sync sổ quỹ


class CongNoCreate(CongNoBase):
    id: Optional[str] = None  # auto-generate nếu thiếu (CN-YYYY-NNNN)


class CongNoUpdate(BaseModel):
    ngay: Optional[date] = None
    doi_tac: Optional[str] = None
    so_tien: Optional[Decimal] = None
    da_tra: Optional[Decimal] = None
    loai: Optional[str] = Field(default=None, pattern="^(phai_thu|phai_tra)$")
    loai_chi_tiet: Optional[str] = None
    ma_don: Optional[str] = None
    ref_id: Optional[str] = None
    ref_source: Optional[str] = None
    han_thanh_toan: Optional[str] = None
    trang_thai: Optional[str] = Field(default=None, pattern="^(chua_tra|da_tra)$")
    ngay_tra: Optional[date] = None
    ghi_chu: Optional[str] = None
    tai_khoan: Optional[str] = None  # Tài khoản chi/thu khi sync sổ quỹ


class CongNoOut(CongNoBase):
    id: str
    con_lai: Optional[Decimal] = None  # GENERATED column
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CongNoTraBody(BaseModel):
    """Body cho POST /cong-no/{id}/tra — đánh dấu trả công nợ.

    Nếu `da_tra` không cung cấp, mặc định = `so_tien` (trả hết).
    `tai_khoan` để ghi sổ quỹ chi/thu tách theo tài khoản ngân hàng / tiền mặt.
    """
    da_tra: Optional[Decimal] = None
    ngay_tra: Optional[date] = None
    ghi_chu: Optional[str] = None
    tai_khoan: Optional[str] = None
