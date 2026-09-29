"""Body các API ghi của màn Thuế TNCN/TNDN và Chi phí chờ phân bổ (2026-09-25)."""
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ThangIn(BaseModel):
    thang: str = Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class QuyIn(BaseModel):
    quy: str = Field(..., pattern=r"^Q[1-4]-\d{4}$")


class DieuChinhDong(BaseModel):
    loai: Literal["tang", "giam"]
    noi_dung: str = Field(..., max_length=200)
    so_tien: int = Field(..., gt=0)


class DieuChinhIn(QuyIn):
    dong: list[DieuChinhDong] = Field(default_factory=list, max_length=50)


class PhanBoIn(BaseModel):
    ten: str = Field(..., max_length=160)
    loai: Literal["tra_truoc", "ccdc"]
    tong: int = Field(..., gt=0)
    so_ky: int
    tk_cp: str = Field(..., max_length=10)
    doi: str = Field(..., max_length=10)
    ngay: Optional[date] = None
    bo_phan: Optional[str] = Field(None, max_length=60)
