"""Pydantic v2 — KhoanVay (vốn vay) request/response."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ─── KhoanVay master ──────────────────────────────────────────────────────────

class KhoanVayCreate(BaseModel):
    ma_khoan: str = Field(min_length=2, max_length=64)
    nguon_vay: str = Field(min_length=1, max_length=128)
    loai_vay: str = Field(default="tin_chap", pattern=r"^(tin_chap|the_chap|tra_gop_xe|tra_gop_nha|khac)$")
    so_tien_vay: Decimal = Field(gt=0)
    ngay_vay: date
    ky_han_thang: int = Field(default=12, ge=1, le=600)
    phuong_thuc_tra: str = Field(
        default="tu_do",
        pattern=r"^(tu_do|tra_deu|chi_lai_dinh_ky|goc_lai_cuoi_ky)$",
    )
    tai_san_the_chap: Optional[str] = None
    tai_khoan_giai_ngan: Optional[str] = None  # tên TK ngân hàng nhận tiền
    # Phase 2 — id của TK NH nhận tiền vay (để post journal Nợ 112 / Có 311|341)
    tai_khoan_id: Optional[int] = Field(default=None, gt=0)
    lai_suat_nam: Decimal = Field(default=Decimal("8.0"), ge=0, le=100)  # initial rate
    auto_giai_ngan: bool = True  # tự tạo so_quy thu khi POST
    ghi_chu: Optional[str] = None


class KhoanVayUpdate(BaseModel):
    nguon_vay: Optional[str] = None
    loai_vay: Optional[str] = Field(
        default=None, pattern=r"^(tin_chap|the_chap|tra_gop_xe|tra_gop_nha|khac)$"
    )
    so_tien_vay: Optional[Decimal] = Field(default=None, gt=0)
    ngay_vay: Optional[date] = None
    ky_han_thang: Optional[int] = Field(default=None, ge=1, le=600)
    phuong_thuc_tra: Optional[str] = Field(
        default=None, pattern=r"^(tu_do|tra_deu|chi_lai_dinh_ky|goc_lai_cuoi_ky)$"
    )
    tai_san_the_chap: Optional[str] = None
    tai_khoan_giai_ngan: Optional[str] = None
    # Khi pass tai_khoan_id và khoản vay CHƯA có giao dịch M4 → backfill
    # (tạo TaiKhoanNHGiaoDich + post journal Nợ 111/112 / Có 311/341).
    tai_khoan_id: Optional[int] = Field(default=None, gt=0)
    status: Optional[str] = Field(
        default=None, pattern=r"^(dang_vay|da_tat_toan|qua_han)$"
    )
    ghi_chu: Optional[str] = None


class KhoanVayLaiSuatOut(BaseModel):
    id: int
    tu_ngay: date
    lai_suat_nam: Decimal
    ghi_chu: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class KhoanVayGiaoDichOut(BaseModel):
    id: int
    loai: str
    ngay: date
    so_tien: Decimal
    so_tien_goc: Optional[Decimal] = None
    so_tien_lai: Optional[Decimal] = None
    ref_so_quy_id: Optional[int] = None
    ref_chi_phi_id: Optional[int] = None
    ghi_chu: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class KhoanVayOut(BaseModel):
    id: int
    ma_khoan: str
    nguon_vay: str
    loai_vay: str
    so_tien_vay: Decimal
    ngay_vay: date
    ky_han_thang: int
    ngay_dao_han: Optional[date] = None
    phuong_thuc_tra: str
    tai_san_the_chap: Optional[str] = None
    tai_khoan_giai_ngan: Optional[str] = None
    status: str
    ghi_chu: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Computed
    da_tra_goc: Decimal = Decimal("0")
    con_lai_goc: Decimal = Decimal("0")
    da_tra_lai: Decimal = Decimal("0")
    lai_suat_hien_tai: Optional[Decimal] = None
    model_config = ConfigDict(from_attributes=True)


class KhoanVayDetailOut(KhoanVayOut):
    lai_suats: list[KhoanVayLaiSuatOut] = []
    giao_dichs: list[KhoanVayGiaoDichOut] = []


# ─── Lãi suất ─────────────────────────────────────────────────────────────────

class LaiSuatCreate(BaseModel):
    tu_ngay: date
    lai_suat_nam: Decimal = Field(ge=0, le=100)
    ghi_chu: Optional[str] = None


# ─── Giao dịch ────────────────────────────────────────────────────────────────

class TraGocBody(BaseModel):
    ngay: date
    so_tien: Decimal = Field(gt=0)
    tai_khoan: Optional[str] = None  # TK trả từ (so_quy.tai_khoan — legacy)
    tai_khoan_id: Optional[int] = Field(default=None, gt=0)  # Phase 2 — TK NH id
    ghi_chu: Optional[str] = None


class TraLaiBody(BaseModel):
    ngay: date
    so_tien: Decimal = Field(gt=0)
    tai_khoan: Optional[str] = None
    tai_khoan_id: Optional[int] = Field(default=None, gt=0)
    ghi_chu: Optional[str] = None


class TraGocLaiBody(BaseModel):
    ngay: date
    so_tien_goc: Decimal = Field(gt=0)
    so_tien_lai: Decimal = Field(ge=0)
    tai_khoan: Optional[str] = None
    tai_khoan_id: Optional[int] = Field(default=None, gt=0)
    ghi_chu: Optional[str] = None
