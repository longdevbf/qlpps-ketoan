"""Pydantic v2 — BaoCaoPLSnapshot output schema."""
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class PLSnapshotOut(BaseModel):
    id: int
    thang: str
    dt_thuan: Optional[Decimal] = None
    cogs: Optional[Decimal] = None
    ln_gop: Optional[Decimal] = None
    cp_ban_hang: Optional[Decimal] = None
    cp_quan_ly: Optional[Decimal] = None
    dt_tai_chinh: Optional[Decimal] = None
    cp_tai_chinh: Optional[Decimal] = None
    thu_nhap_khac: Optional[Decimal] = None
    cp_khac: Optional[Decimal] = None
    ln_truoc_thue: Optional[Decimal] = None
    thue_tndn: Optional[Decimal] = None
    lnst: Optional[Decimal] = None
    raw_breakdown: Optional[dict[str, Any]] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
