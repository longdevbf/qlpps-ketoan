"""Pydantic schemas — BaoCaoSnapshot."""
from datetime import datetime, date
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class BaoCaoSnapshotBase(BaseModel):
    thang: date
    data: dict[str, Any]


class BaoCaoSnapshotOut(BaoCaoSnapshotBase):
    id: int
    created_at: datetime
    created_by: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
