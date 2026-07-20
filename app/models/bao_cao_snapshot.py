"""BaoCaoSnapshot — snapshot full P&L theo tháng (JSONB).

Dùng để chốt sổ tháng + so sánh kỳ trước. UNIQUE (thang).
"""
from datetime import datetime, date
from typing import Any, Optional

from sqlalchemy import Date, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class BaoCaoSnapshot(Base):
    __tablename__ = "bao_cao_snapshot"
    __table_args__ = ({"schema": "ketoan"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thang: Mapped[date] = mapped_column(Date, nullable=False, unique=True)  # yyyy-mm-01
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[Optional[str]] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<BaoCaoSnapshot {self.id} {self.thang}>"
