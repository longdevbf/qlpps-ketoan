"""Pydantic schemas — Journal Entry / Journal Line (double-entry)."""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


_LOAI_LINE_PATTERN = r"^(no|co)$"


class JournalLineIn(BaseModel):
    loai: str = Field(pattern=_LOAI_LINE_PATTERN)
    account_code: str = Field(min_length=1, max_length=20)
    account_name: Optional[str] = Field(default=None, max_length=255)
    ref_table: Optional[str] = Field(default=None, max_length=64)
    ref_id: Optional[int] = None
    so_tien: Decimal = Field(gt=0)
    ghi_chu: Optional[str] = None


class JournalLineOut(BaseModel):
    id: int
    loai: str
    account_code: str
    account_name: Optional[str] = None
    ref_table: Optional[str] = None
    ref_id: Optional[int] = None
    so_tien: Decimal
    ghi_chu: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class JournalEntryIn(BaseModel):
    """Body cho POST /api/journal — tạo bút toán manual."""
    ngay: date
    mo_ta: Optional[str] = None
    source_type: Optional[str] = Field(default="other", max_length=40)
    source_id: Optional[str] = Field(default=None, max_length=64)
    lines: List[JournalLineIn] = Field(min_length=2)


class JournalEntryOut(BaseModel):
    id: int
    ma_but_toan: str
    ngay: date
    mo_ta: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    tong_tien: Decimal
    trang_thai: str
    created_by: Optional[str] = None
    created_at: datetime
    lines: List[JournalLineOut] = []
    model_config = ConfigDict(from_attributes=True)


class JournalEntrySummary(BaseModel):
    """Item trong list (không kèm lines)."""
    id: int
    ma_but_toan: str
    ngay: date
    mo_ta: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    tong_tien: Decimal
    trang_thai: str
    created_by: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AccountInfo(BaseModel):
    code: str
    name: str
