"""Pydantic schemas — TaiKhoanNHGiaoDich (nhật ký thu/chi tài khoản NH)."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


_LOAI_PATTERN = r"^(thu|chi)$"


class TaiKhoanNHGiaoDichCreate(BaseModel):
    ngay: date
    loai: str = Field(pattern=_LOAI_PATTERN)
    so_tien: Decimal = Field(gt=0)
    doi_tac: Optional[str] = Field(default=None, max_length=255)
    ghi_chu: Optional[str] = None
    source_app: Optional[str] = Field(default=None, max_length=32)
    source_doc_id: Optional[str] = Field(default=None, max_length=64)
    # Phase 2 — sinh thêm journal entry minh bạch (mặc định: false vì
    # bản thân tknhgd manual đã đại diện 1 vế, đối ứng còn lại không rõ ngữ cảnh).
    gen_journal: bool = False
    # Tài khoản đối ứng nếu gen_journal=True
    # (vd thu vốn → 411, thu khác → 711, chi → 811 ...)
    counter_account: Optional[str] = Field(default=None, max_length=20)


class TaiKhoanNHGiaoDichOut(BaseModel):
    id: int
    ngay: date
    tai_khoan_id: int
    loai: str
    so_tien: Decimal
    doi_tac: Optional[str] = None
    ghi_chu: Optional[str] = None
    source_app: Optional[str] = None
    source_doc_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    # Computed (running balance) — chỉ điền trong list endpoint
    so_du_sau: Optional[Decimal] = None
    model_config = ConfigDict(from_attributes=True)


class TaiKhoanSoDuOut(BaseModel):
    tai_khoan_id: int
    so_du: Decimal
    tong_thu: Decimal
    tong_chi: Decimal
    so_giao_dich: int
