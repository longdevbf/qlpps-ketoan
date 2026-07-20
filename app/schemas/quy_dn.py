"""Pydantic schemas — Quỹ DN."""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class QuyDNCreate(BaseModel):
    ten_quy: str = Field(min_length=1, max_length=128)
    so_du: Decimal = Field(default=Decimal("0"), ge=0)
    ghi_chu: Optional[str] = None
    active: bool = True


class QuyDNUpdate(BaseModel):
    ten_quy: Optional[str] = Field(default=None, min_length=1, max_length=128)
    so_du: Optional[Decimal] = Field(default=None, ge=0)
    ghi_chu: Optional[str] = None
    active: Optional[bool] = None


class QuyDNOut(BaseModel):
    id: int
    ten_quy: str
    so_du: Decimal
    ghi_chu: Optional[str] = None
    active: bool
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
