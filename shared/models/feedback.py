"""Customer feedback — phản hồi của KH ingest từ Pancake/Zalo/FB hoặc app dept.

Phân loại tự động bằng từ khoá → severity + category. CEO + trưởng phòng
xem heatmap, bar SP bị phàn nàn, line SLA xử lý.

source:    'pancake' | 'zalo' | 'fb' | 'manual' | 'vc'
severity:  'low' | 'med' | 'high' | 'critical'
category:  'san_pham' | 'dich_vu' | 'giao_hang' | 'ke_toan' | 'khac'
status:    'new' | 'processing' | 'resolved' | 'rejected'
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, BigInteger, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        Index("ix_feedback_status", "status"),
        Index("ix_feedback_severity", "severity"),
        Index("ix_feedback_category", "category"),
        Index("ix_feedback_source", "source"),
        Index("ix_feedback_created", "created_at"),
        Index("ix_feedback_customer", "customer_id"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(128))
    customer_id: Mapped[Optional[str]] = mapped_column(String(64))
    customer_name: Mapped[Optional[str]] = mapped_column(String(255))
    customer_phone: Mapped[Optional[str]] = mapped_column(String(32))
    app: Mapped[Optional[str]] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16), default="med", nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="khac", nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    san_pham: Mapped[Optional[str]] = mapped_column(String(255))
    extra: Mapped[Optional[dict]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="new", nullable=False)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(64))
    assigned_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shared.users.id"))
    resolution: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
