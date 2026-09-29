"""Pydantic schemas — ChiPhiPhatSinh."""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ChiPhiBase(BaseModel):
    ngay: date
    so_tien: Decimal = Decimal("0")
    loai_chi_phi: Optional[str] = None
    ten_khoan: Optional[str] = None  # Issue 2 — tên cụ thể vd "Mua VPP tháng 4"
    nhom_chi_phi: str = "khac"  # ban_hang | quan_ly | tai_chinh | khac
    quy: Optional[str] = None
    phong_ban: Optional[str] = None
    nguoi_chi: Optional[str] = None
    don_vi_vc: Optional[str] = None
    ma_don: Optional[str] = None
    ngan_hang: Optional[str] = None
    hoa_don_url: Optional[str] = None
    mo_ta: Optional[str] = None
    ghi_chu: Optional[str] = None
    ref_vc: Optional[str] = None
    ref_payroll_thang_pb: Optional[str] = None  # 'YYYY-MM' (ứng lương) hoặc 'PAYROLL-...' (bridge)


class ChiPhiCreate(ChiPhiBase):
    """Phase 2 (double-entry):
      - Nếu truyền `tai_khoan_id` → Nợ <account_cp> / Có 112 (TK), đồng thời
        insert tknhgd loai='chi' để TK NH giảm.
      - Nếu truyền `cong_no_ncc_id` → Nợ <account_cp> / Có 331 (cong_no).
      - Nếu cả hai → ưu tiên `tai_khoan_id`.
    Account chi phí được suy từ `nhom_chi_phi`:
      ban_hang→641, quan_ly→642, tai_chinh→635, khac→811.
    """
    tai_khoan_id: Optional[int] = None
    cong_no_ncc_id: Optional[str] = None
    # Kỳ lương (chỉ dùng cho 'Ứng Lương'): 'YYYY-MM' — ứng cho tháng lương nào.
    # Lưu vào cột ref_payroll_thang_pb; HCNS payroll trừ theo kỳ này (không theo ngày).
    ky_luong: Optional[str] = None


class ChiPhiUpdate(BaseModel):
    ngay: Optional[date] = None
    so_tien: Optional[Decimal] = None
    loai_chi_phi: Optional[str] = None
    ten_khoan: Optional[str] = None
    nhom_chi_phi: Optional[str] = None
    quy: Optional[str] = None
    phong_ban: Optional[str] = None
    nguoi_chi: Optional[str] = None
    don_vi_vc: Optional[str] = None
    ma_don: Optional[str] = None
    ngan_hang: Optional[str] = None
    hoa_don_url: Optional[str] = None
    mo_ta: Optional[str] = None
    ghi_chu: Optional[str] = None
    ky_luong: Optional[str] = None  # 'YYYY-MM' → ref_payroll_thang_pb (ứng lương)


class ChiPhiOut(ChiPhiBase):
    id: int
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    nguon: Optional[str] = None  # nguồn: "KT tự nhập" | "Đề xuất chi" | "Đề Nghị TT" | ...
    model_config = ConfigDict(from_attributes=True)
