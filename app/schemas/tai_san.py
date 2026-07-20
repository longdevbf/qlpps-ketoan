"""Pydantic v2 — Tài Sản Cố Định + Khấu Hao (Phase 3)."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ─── TSCĐ ─────────────────────────────────────────────────────────────────────

_LOAI_PATTERN = r"^(huu_hinh|vo_hinh)$"
_BO_PHAN_PATTERN = r"^(ban_hang|quan_ly|tai_chinh|khac)$"
_TRANG_THAI_PATTERN = r"^(dang_su_dung|da_thanh_ly|hong)$"


class TSCDCreate(BaseModel):
    ten_tscd: str = Field(min_length=1, max_length=255)
    loai: str = Field(default="huu_hinh", pattern=_LOAI_PATTERN)
    nhom: Optional[str] = Field(default=None, max_length=64)
    ngay_mua: date
    ngay_su_dung: date
    nguyen_gia: Decimal = Field(gt=0)
    chi_phi_lap_dat: Decimal = Field(default=Decimal("0"), ge=0)
    so_thang_kh: int = Field(ge=1, le=600)
    bo_phan: str = Field(default="quan_ly", pattern=_BO_PHAN_PATTERN)
    ncc: Optional[str] = Field(default=None, max_length=255)
    source_doc_id: Optional[str] = Field(default=None, max_length=64)
    ghi_chu: Optional[str] = None
    hinh_anh: Optional[str] = None
    # TK chi tiền (để post journal Nợ 211|213 / Có 111|112) — optional;
    # nếu không truyền thì chỉ ghi nhận TSCĐ, không sinh JE mua.
    tai_khoan_id: Optional[int] = Field(default=None, gt=0)


class TSCDUpdate(BaseModel):
    ten_tscd: Optional[str] = Field(default=None, min_length=1, max_length=255)
    loai: Optional[str] = Field(default=None, pattern=_LOAI_PATTERN)
    nhom: Optional[str] = Field(default=None, max_length=64)
    ngay_mua: Optional[date] = None
    ngay_su_dung: Optional[date] = None
    # nguyen_gia / chi_phi_lap_dat / so_thang_kh chỉ cho phép sửa khi CHƯA có khấu hao (router check).
    nguyen_gia: Optional[Decimal] = Field(default=None, gt=0)
    chi_phi_lap_dat: Optional[Decimal] = Field(default=None, ge=0)
    so_thang_kh: Optional[int] = Field(default=None, ge=1, le=600)
    bo_phan: Optional[str] = Field(default=None, pattern=_BO_PHAN_PATTERN)
    ncc: Optional[str] = Field(default=None, max_length=255)
    source_doc_id: Optional[str] = Field(default=None, max_length=64)
    ghi_chu: Optional[str] = None
    hinh_anh: Optional[str] = None
    trang_thai: Optional[str] = Field(default=None, pattern=_TRANG_THAI_PATTERN)


class TSCDOut(BaseModel):
    id: int
    ma_tscd: str
    ten_tscd: str
    loai: str
    nhom: Optional[str] = None
    ngay_mua: date
    ngay_su_dung: date
    nguyen_gia: Decimal
    chi_phi_lap_dat: Decimal = Decimal("0")
    so_thang_kh: int
    phuong_phap: str
    hao_mon_luy_ke: Decimal
    account_code: str
    bo_phan: str
    ncc: Optional[str] = None
    source_doc_id: Optional[str] = None
    trang_thai: str
    ngay_thanh_ly: Optional[date] = None
    gia_thanh_ly: Optional[Decimal] = None
    ghi_chu: Optional[str] = None
    hinh_anh: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Computed
    gia_tri_con_lai: Decimal = Decimal("0")
    so_tien_kh_thang: Decimal = Decimal("0")
    so_thang_da_kh: int = 0
    model_config = ConfigDict(from_attributes=True)


# ─── KhauHaoLog ───────────────────────────────────────────────────────────────

class KhauHaoLogOut(BaseModel):
    id: int
    tscd_id: int
    thang: str
    so_tien: Decimal
    hao_mon_luy_ke_sau: Decimal
    journal_id: Optional[int] = None
    ghi_chu: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    # join info (optional)
    ma_tscd: Optional[str] = None
    ten_tscd: Optional[str] = None
    nhom: Optional[str] = None
    bo_phan: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class TSCDDetailOut(TSCDOut):
    khau_hao_logs: list[KhauHaoLogOut] = []


class ChayKhauHaoItem(BaseModel):
    tscd_id: int
    ma_tscd: str
    ten_tscd: str
    so_tien_kh: Decimal
    hao_mon_luy_ke_sau: Decimal
    journal_id: Optional[int] = None
    log_id: int


class ChayKhauHaoSkipped(BaseModel):
    tscd_id: int
    ma_tscd: str
    ten_tscd: str
    ly_do: str  # 'da_khau_hao' | 'da_khau_hao_het' | 'da_thanh_ly' | 'chua_su_dung'


class ChayKhauHaoResponse(BaseModel):
    thang: str
    da_xu_ly: int
    tong_kh: Decimal
    items: list[ChayKhauHaoItem] = []
    skipped: list[ChayKhauHaoSkipped] = []


# ─── Thanh lý ─────────────────────────────────────────────────────────────────

class ThanhLyBody(BaseModel):
    ngay_thanh_ly: date
    gia_thanh_ly: Decimal = Field(ge=0)  # có thể bằng 0 nếu phế liệu/cho không
    tai_khoan_id: Optional[int] = Field(default=None, gt=0)
    ghi_chu: Optional[str] = None


# ─── Summary ──────────────────────────────────────────────────────────────────

class TSCDSummaryGroup(BaseModel):
    key: str
    nguyen_gia: Decimal
    hao_mon_luy_ke: Decimal
    gia_tri_con_lai: Decimal
    n_tscd: int


class TSCDSummary(BaseModel):
    tong_nguyen_gia: Decimal
    tong_hao_mon: Decimal
    tong_con_lai: Decimal
    n_dang_su_dung: int
    n_da_thanh_ly: int
    n_hong: int
    by_loai: list[TSCDSummaryGroup] = []
    by_nhom: list[TSCDSummaryGroup] = []
    by_bo_phan: list[TSCDSummaryGroup] = []
