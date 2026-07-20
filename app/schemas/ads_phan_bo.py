"""Pydantic schemas — AdsPhanBoDon (Phase 6A)."""
from datetime import date as date_cls, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AdsPhanBoDonOut(BaseModel):
    id: int
    thang_chi_ads: str
    nhom_master: str
    quote_number: Optional[str] = None
    ngay_chot: Optional[date_cls] = None
    value_nhom_trong_don: Optional[Decimal] = None
    ty_le_pool: Optional[Decimal] = None
    so_tien_phan_bo: Decimal
    loai_phan_bo: str
    vc_status: Optional[str] = None
    thang_hoan_thanh: Optional[str] = None
    cpa_nhom_snapshot: Optional[Decimal] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdsPhanBoSummary(BaseModel):
    """Tóm tắt 1 tháng phân bổ ads — trả từ /summary và /recalc."""
    thang: str
    ads_total: float = 0.0
    ads_by_nhom: dict[str, float] = Field(default_factory=dict)
    ads_unmatched: float = 0.0
    pool_after_redistribute: dict[str, float] = Field(default_factory=dict)
    n_quotes_chot: int = 0
    rows_inserted: int = 0
    no_match_pools: list[dict] = Field(default_factory=list)


class AdsPhanBoCohortRow(BaseModel):
    """1 ô ma trận tháng_chi × tháng_hoàn_thành."""
    thang_chi_ads: str
    thang_hoan_thanh: Optional[str] = None
    nhom_master: str
    so_tien_phan_bo: float
    so_dong: int


class AdsPhanBoCohort(BaseModel):
    tu: str
    den: str
    rows: list[AdsPhanBoCohortRow]
