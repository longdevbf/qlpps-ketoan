"""Pydantic v2 — KyKeToan + ChotKy response schemas."""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict

from .pl_snapshot import PLSnapshotOut


class KyKeToanOut(BaseModel):
    thang: str
    trang_thai: str
    chot_luc: Optional[datetime] = None
    chot_boi: Optional[str] = None
    pl_snapshot_id: Optional[int] = None
    ln_giu_lai_dau_ky: Optional[Decimal] = Decimal("0")
    lnst_ky: Optional[Decimal] = None
    ln_giu_lai_cuoi_ky: Optional[Decimal] = None
    co_tuc_da_chia: Optional[Decimal] = Decimal("0")
    trich_quy_ky: Optional[Decimal] = Decimal("0")
    ghi_chu: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class KyKeToanDetailOut(KyKeToanOut):
    """Detail kèm snapshot P&L."""
    pl_snapshot: Optional[PLSnapshotOut] = None


class ChotKyResponse(BaseModel):
    ok: bool = True
    thang: str
    trang_thai: str
    pl_snapshot_id: Optional[int] = None
    ln_giu_lai_dau_ky: Decimal
    lnst_ky: Decimal
    co_tuc_da_chia: Decimal
    trich_quy_ky: Decimal
    ln_giu_lai_cuoi_ky: Decimal
    chot_luc: datetime
    chot_boi: str


class LNGiuLaiLuyKeOut(BaseModel):
    """LN giữ lại lũy kế tới hiện tại — bằng `ln_giu_lai_cuoi_ky` của kỳ chốt mới nhất."""
    ky_chot_moi_nhat: Optional[str] = None
    ln_giu_lai_luy_ke: Decimal = Decimal("0")
    n_ky_da_chot: int = 0
