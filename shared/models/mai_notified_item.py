"""MaiNotifiedItem — log Mai đã DM NV về 1 đơn pending.

UNIQUE (item_source, item_ref_id) → mỗi đơn chỉ DM 1 lần.

item_source : 'duyet_chi' | 'xin_nghi' | 'baogia_quote' | 'muahang_po'
              | 'marketing_km' | 'denghitt' | 'lenh_di_do' | 'shared_approval' | ...
item_ref_id : id của item (string hoá vì có nguồn dùng numeric, có nguồn dùng string).
decision    : 'auto_approve' | 'escalate' | 'skip' — Mai quyết gì cho đơn này.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class MaiNotifiedItem(Base):
    __tablename__ = "mai_notified_items"
    __table_args__ = (
        UniqueConstraint("item_source", "item_ref_id", name="ux_mai_notified_items_src_ref"),
        Index("ix_mai_notified_source", "item_source"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    item_source: Mapped[str] = mapped_column(String(32), nullable=False)
    item_ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)

    requested_by_username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dm_room_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dm_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    notified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
