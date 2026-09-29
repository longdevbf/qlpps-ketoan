"""Pydantic v2 — Cài đặt Kế toán (đơn vị, chính sách, đánh số chứng từ).

Tab "Duyệt chi" + "Phân quyền" KHÔNG có schema PUT — 2 tab đó chỉ đọc, dữ liệu
lấy trực tiếp từ code phân quyền thật (xem `app/routers/cai_dat.py`), không
lưu bảng riêng (anh Quang 2026-09-25, xem README mục 4.30).
"""
import re
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_MST_RE = re.compile(r"^\d{10}(-\d{3})?$")

_CHE_DO_HOP_LE = {"tt99", "tt133"}
_GIA_XUAT_KHO_HOP_LE = {
    "binh_quan_cuoi_ky", "binh_quan_tuc_thoi", "fifo", "dich_danh",
}
_KHAU_HAO_HOP_LE = {"duong_thang", "so_du_giam_dan", "san_luong"}
_KY_KE_KHAI_HOP_LE = {"thang", "quy"}
_THANG_HOP_LE = {f"{i:02d}" for i in range(1, 13)}
_LAM_LAI_HOP_LE = {"khong", "nam", "thang"}


class DonViIn(BaseModel):
    """PUT /api/cai-dat/don_vi — cũng dùng tạo lại GET /api/don-vi cho trang in."""

    ten: str = Field(..., max_length=200)
    ten_ngan: Optional[str] = Field(None, max_length=40)
    mst: Optional[str] = Field(None, max_length=14)
    dien_thoai: Optional[str] = Field(None, max_length=20)
    dia_chi: Optional[str] = Field(None, max_length=240)
    email: Optional[str] = Field(None, max_length=120)
    giam_doc: Optional[str] = Field(None, max_length=80)
    ke_toan_truong: Optional[str] = Field(None, max_length=80)
    thu_quy: Optional[str] = Field(None, max_length=80)

    @field_validator("ten")
    @classmethod
    def _ten_khong_rong(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Nhập tên đơn vị")
        return v

    @field_validator("mst")
    @classmethod
    def _chuan_mst(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v = v.strip()
        if not _MST_RE.match(v):
            raise ValueError(
                'Mã số thuế gồm 10 chữ số (chi nhánh thêm "-" và 3 số)'
            )
        return v

    @field_validator(
        "ten_ngan", "dien_thoai", "dia_chi", "email",
        "giam_doc", "ke_toan_truong", "thu_quy",
        mode="before",
    )
    @classmethod
    def _rong_thanh_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v.strip() if isinstance(v, str) else v


class KeToanSettingsIn(BaseModel):
    """PUT /api/cai-dat/ke_toan — chế độ/kỳ kế toán + chính sách."""

    che_do: str
    nam_tc_bat_dau: str
    tien_te: Optional[str] = "VND"
    ngay_bat_dau_dung: Optional[date] = None
    gia_xuat_kho: str
    khau_hao: str
    ky_ke_khai_thue: str

    @field_validator("che_do")
    @classmethod
    def _v_che_do(cls, v):
        if v not in _CHE_DO_HOP_LE:
            raise ValueError(f"Chế độ kế toán không hợp lệ: {v!r}")
        return v

    @field_validator("nam_tc_bat_dau")
    @classmethod
    def _v_nam_tc(cls, v):
        if v not in _THANG_HOP_LE:
            raise ValueError('Năm tài chính bắt đầu từ phải là tháng "01".."12"')
        return v

    @field_validator("gia_xuat_kho")
    @classmethod
    def _v_gia_xuat_kho(cls, v):
        if v not in _GIA_XUAT_KHO_HOP_LE:
            raise ValueError(f"Phương pháp tính giá xuất kho không hợp lệ: {v!r}")
        return v

    @field_validator("khau_hao")
    @classmethod
    def _v_khau_hao(cls, v):
        if v not in _KHAU_HAO_HOP_LE:
            raise ValueError(f"Phương pháp khấu hao không hợp lệ: {v!r}")
        return v

    @field_validator("ky_ke_khai_thue")
    @classmethod
    def _v_ky_ke_khai(cls, v):
        if v not in _KY_KE_KHAI_HOP_LE:
            raise ValueError(f"Kỳ kê khai thuế GTGT không hợp lệ: {v!r}")
        return v


class DanhSoRuleIn(BaseModel):
    """1 dòng quy tắc đánh số trong PUT /api/cai-dat/danh_so (body = list các dòng)."""

    ma: str = Field(..., max_length=30)
    ten: str = Field(..., max_length=60)
    tien_to: str = Field("", max_length=8)
    do_dai: int
    lam_lai: str

    @field_validator("tien_to", mode="before")
    @classmethod
    def _chuan_tien_to(cls, v):
        return (str(v or "")).strip().upper().replace(" ", "")

    @field_validator("do_dai")
    @classmethod
    def _v_do_dai(cls, v):
        if v not in (3, 4, 5, 6):
            raise ValueError("Số chữ số phải là 3, 4, 5 hoặc 6")
        return v

    @field_validator("lam_lai")
    @classmethod
    def _v_lam_lai(cls, v):
        if v not in _LAM_LAI_HOP_LE:
            raise ValueError(f"Đánh lại số không hợp lệ: {v!r}")
        return v
