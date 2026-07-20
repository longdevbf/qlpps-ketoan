"""Pydantic schemas — Báo Cáo Tổng Hợp (P&L) + grouped aggregates."""
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class BaoCaoRequest(BaseModel):
    """Query params cho mọi endpoint /api/bao-cao/*."""
    tu_ngay: Optional[date] = None        # nếu None → từ đầu tháng hiện tại
    den_ngay: Optional[date] = None       # nếu None → đến hôm nay
    loai: Optional[str] = None            # filter theo loại (cho /chi-phi, /doanh-thu)


class GroupedAmount(BaseModel):
    """1 nhóm trong aggregate (group by ngay/thang/loai/nv)."""
    key: str = Field(..., description="ngày YYYY-MM-DD / tháng YYYY-MM / tên loại")
    so_tien: Decimal = Decimal("0")
    so_phieu: int = 0


class BaoCaoTongHopOut(BaseModel):
    """P&L summary trong khoảng [tu_ngay, den_ngay]."""
    tu_ngay: date
    den_ngay: date

    # Doanh thu
    tong_doanh_thu: Decimal = Decimal("0")
    so_phieu_thu: int = 0

    # Chi phí
    tong_chi_phi_phat_sinh: Decimal = Decimal("0")
    tong_chi_phi_co_dinh: Decimal = Decimal("0")
    so_phieu_chi: int = 0

    # External (cross-app)
    tong_luong_hcns: Decimal = Decimal("0")
    tong_ads_marketing: Decimal = Decimal("0")
    tong_don_hang_muahang: Decimal = Decimal("0")

    # Aggregates
    tong_chi_phi: Decimal = Decimal("0")
    loi_nhuan_gop: Decimal = Decimal("0")               # doanh_thu - chi_phi_ps - chi_phi_cd
    loi_nhuan_truoc_thue: Decimal = Decimal("0")        # gồm cả lương + ads

    # ----- Breakdown (Sprint Week 12) -----
    luong_by_phong_ban: dict[str, float] = Field(default_factory=dict)
    chi_phi_by_phong_ban: dict[str, float] = Field(default_factory=dict)
    chi_phi_by_quy: dict[str, float] = Field(default_factory=dict)
    ads_by_kenh: dict[str, float] = Field(default_factory=dict)
    doanh_thu_by_loai_tt: dict[str, float] = Field(default_factory=dict)


class BaoCaoCongNoOut(BaseModel):
    """Tổng phải thu / phải trả + breakdown."""
    tu_ngay: date
    den_ngay: date
    tong_phai_thu: Decimal = Decimal("0")
    tong_phai_tra: Decimal = Decimal("0")
    so_no_phai_thu: int = 0
    so_no_phai_tra: int = 0
    by_doi_tac: list[GroupedAmount] = []
