"""Pydantic schemas — Vốn Chủ Sở Hữu (VCSH)."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


_LOAI_PATTERN = r"^(gop_von|rut_von|chia_co_tuc|trich_quy|dieu_chinh)$"


class VonCSHBase(BaseModel):
    ngay: date
    so_tien: Decimal = Field(gt=0)
    chu_so_huu: Optional[str] = Field(default=None, max_length=128)
    ghi_chu: Optional[str] = None
    source_doc_id: Optional[str] = Field(default=None, max_length=64)


class GopVonBody(VonCSHBase):
    """gop_von / rut_von / chia_co_tuc — body chung.

    Phase 2 (double-entry): nếu truyền `tai_khoan_id` → auto post journal:
      - gop_von:        Nợ 112 (TK) / Có 411 (vốn góp) + insert tknhgd thu
      - rut_von:        Nợ 411 / Có 112 + insert tknhgd chi
      - chia_co_tuc:    Nợ 421 / Có 112 + insert tknhgd chi
    """
    tai_khoan_id: Optional[int] = Field(default=None, gt=0)


class TrichQuyBody(VonCSHBase):
    """trich_quy phải kèm quy_id (1 quỹ active).

    Phase 2: tự post journal Nợ 421 / Có 414|415|353 (theo tên quỹ).
    """
    quy_id: int = Field(gt=0)


class KhoiTaoBanDauBody(BaseModel):
    """Khởi tạo vốn ban đầu — chỉ chạy 1 lần.

    Phase 2: nếu truyền `tai_khoan_id` → auto post journal Nợ 112 / Có 411.
    """
    ngay: date
    so_tien: Decimal = Field(gt=0)
    chu_so_huu: Optional[str] = Field(default=None, max_length=128)
    ghi_chu: Optional[str] = None
    tai_khoan_id: Optional[int] = Field(default=None, gt=0)


class VonCSHCreate(VonCSHBase):
    loai_giao_dich: str = Field(pattern=_LOAI_PATTERN)
    quy_id: Optional[int] = None


class VonCSHUpdate(BaseModel):
    ngay: Optional[date] = None
    loai_giao_dich: Optional[str] = Field(default=None, pattern=_LOAI_PATTERN)
    so_tien: Optional[Decimal] = Field(default=None, gt=0)
    chu_so_huu: Optional[str] = None
    quy_id: Optional[int] = None
    ghi_chu: Optional[str] = None
    source_doc_id: Optional[str] = None


class VonCSHOut(VonCSHBase):
    id: int
    loai_giao_dich: str
    quy_id: Optional[int] = None
    created_by: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class QuyDNSummaryItem(BaseModel):
    id: int
    ten_quy: str
    so_du: Decimal


class VonCSHSummary(BaseModel):
    tong_gop_von: Decimal = Decimal("0")
    tong_rut_von: Decimal = Decimal("0")
    tong_chia_co_tuc: Decimal = Decimal("0")
    tong_trich_quy: Decimal = Decimal("0")
    tong_dieu_chinh: Decimal = Decimal("0")
    von_gop_hien_tai: Decimal = Decimal("0")
    quy_dn: list[QuyDNSummaryItem] = []
