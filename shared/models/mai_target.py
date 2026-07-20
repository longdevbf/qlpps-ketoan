"""MaiTarget — target/goal cho Mai AI evaluate %.

scope        : 'company' | 'department' | 'employee'
scope_value  : NULL khi scope='company'; tên phòng khi 'department';
               username khi 'employee'.
metric       : 'doanh_thu' | 'leads' | 'don_hang' | 'kpi' (mở rộng tự do).
period_type  : 'month' | 'quarter' | 'year'
period_value : '2026-05' | '2026-Q2' | '2026'
target_value : số NGUYÊN (đồng / count) — Numeric(15,0).
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class MaiTarget(Base):
    __tablename__ = "mai_targets"
    __table_args__ = ({"schema": "shared"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_value: Mapped[Optional[str]] = mapped_column(Text)

    metric: Mapped[str] = mapped_column(Text, nullable=False)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    period_value: Mapped[str] = mapped_column(Text, nullable=False)

    target_value: Mapped[Decimal] = mapped_column(Numeric(15, 0), nullable=False)

    created_by: Mapped[Optional[str]] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
