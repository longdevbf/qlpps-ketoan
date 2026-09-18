"""Pydantic schemas — ChiPhiCoDinh."""
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# Phase 5C — 6 enum phương pháp phân bổ chi phí
VALID_PHUONG_PHAP_PHAN_BO = {
    "duong_thang",       # 5A — chia đều theo tháng (default, legacy)
    "prorated_by_day",   # 5B — chia theo ngày (overlap_days/30)
    "front_loaded",      # 5C — đầu nặng đuôi nhẹ (50% T1, 50%/(N-1) còn lại)
    "seasonal",          # 5C — trọng số mùa Tết (T11/T12/T01/T02 = 60%; T3..T10 = 40%/8)
    "by_revenue_pct",    # 5C — % doanh thu thực hiện (so_tien_thang = % vd 5)
    "manual",            # 5C — nhập tay JSONB tỷ lệ % cho 12 tháng
}


class CoDinhBase(BaseModel):
    thang_bat_dau: date
    # Phase 5B: prorated theo ngày — chính xác hơn `thang_bat_dau`
    ngay_bat_dau: Optional[date] = None  # nếu None, fallback `thang_bat_dau` ở router
    ngay_ket_thuc: Optional[date] = None  # NULL = vô thời hạn (kết hợp lap_lai)
    so_tien_thang: Decimal = Decimal("0")
    loai_chi_phi: Optional[str] = None
    ten_khoan: Optional[str] = None  # Issue 2 — tên cụ thể vd "Thuê showroom Q3 — 4/2026"
    nhom_chi_phi: str = "khac"  # ban_hang | quan_ly | tai_chinh | khac
    mo_ta: Optional[str] = None
    ghi_chu: Optional[str] = None
    lap_lai: bool = True
    # Phase 4 P&L — phân bổ định phí (1 = chỉ tháng đó / hoặc hàng tháng nếu lap_lai;
    # >1 = chia đều so_tien_thang cho N tháng liên tiếp).
    so_thang_phan_bo: int = Field(default=1, ge=1, description="Số tháng phân bổ (≥1)")
    # Phase 5C — Phương pháp phân bổ (1 trong 6 enum); default 'duong_thang'
    phuong_phap_phan_bo: str = Field(
        default="duong_thang",
        description=(
            "duong_thang | prorated_by_day | front_loaded | "
            "seasonal | by_revenue_pct | manual"
        ),
    )
    # Phase 5C — JSONB tỷ lệ % tháng cho method='manual'
    # Format: {"01": 10, "02": 5, ..., "12": 15} hoặc {"YYYY-MM": pct}
    phan_bo_manual: Optional[dict[str, Any]] = None

    @field_validator("phuong_phap_phan_bo")
    @classmethod
    def _check_method(cls, v: str) -> str:
        if v not in VALID_PHUONG_PHAP_PHAN_BO:
            raise ValueError(
                f"phuong_phap_phan_bo phải thuộc {sorted(VALID_PHUONG_PHAP_PHAN_BO)}"
            )
        return v

    @model_validator(mode="after")
    def _check_ngay_range(self):
        if self.ngay_bat_dau and self.ngay_ket_thuc:
            if self.ngay_ket_thuc < self.ngay_bat_dau:
                raise ValueError("ngay_ket_thuc phải >= ngay_bat_dau")
        # Phase 5C: nếu method='manual' yêu cầu phan_bo_manual phải có data hợp lệ.
        if self.phuong_phap_phan_bo == "manual":
            if not self.phan_bo_manual or not isinstance(self.phan_bo_manual, dict):
                raise ValueError(
                    "method='manual' yêu cầu phan_bo_manual là dict {month: pct}"
                )
        return self


class CoDinhCreate(CoDinhBase):
    """Phase 2 (double-entry): nếu truyền `tai_khoan_id` hoặc `cong_no_ncc_id`,
    sẽ post journal Nợ 641|642|635|811 / Có 112 hoặc 331.
    """
    tai_khoan_id: Optional[int] = None
    cong_no_ncc_id: Optional[str] = None


class CoDinhUpdate(BaseModel):
    thang_bat_dau: Optional[date] = None
    ngay_bat_dau: Optional[date] = None
    ngay_ket_thuc: Optional[date] = None
    so_tien_thang: Optional[Decimal] = None
    loai_chi_phi: Optional[str] = None
    ten_khoan: Optional[str] = None
    nhom_chi_phi: Optional[str] = None
    mo_ta: Optional[str] = None
    ghi_chu: Optional[str] = None
    lap_lai: Optional[bool] = None
    so_thang_phan_bo: Optional[int] = Field(default=None, ge=1)
    # Phase 5C — partial update method + manual JSONB
    phuong_phap_phan_bo: Optional[str] = None
    phan_bo_manual: Optional[dict[str, Any]] = None

    @field_validator("phuong_phap_phan_bo")
    @classmethod
    def _check_method(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in VALID_PHUONG_PHAP_PHAN_BO:
            raise ValueError(
                f"phuong_phap_phan_bo phải thuộc {sorted(VALID_PHUONG_PHAP_PHAN_BO)}"
            )
        return v

    @model_validator(mode="after")
    def _check_ngay_range(self):
        if self.ngay_bat_dau and self.ngay_ket_thuc:
            if self.ngay_ket_thuc < self.ngay_bat_dau:
                raise ValueError("ngay_ket_thuc phải >= ngay_bat_dau")
        # Phase 5C: nếu update set method='manual' thì cần phan_bo_manual đi kèm
        # (hoặc đã có sẵn ở DB — router có thể merge; ở schema chỉ check khi cả 2
        # cùng được nhập)
        if self.phuong_phap_phan_bo == "manual" and self.phan_bo_manual is not None:
            if not isinstance(self.phan_bo_manual, dict):
                raise ValueError(
                    "phan_bo_manual phải là dict {month: pct}"
                )
        return self


class CoDinhOut(CoDinhBase):
    id: int
    created_by: Optional[str] = None
    created_by_ten: Optional[str] = None  # tên NV tra từ username, router setattr trước khi trả
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
