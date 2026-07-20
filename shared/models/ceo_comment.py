"""CEO comments — bút phê CEO ghi vào 1 entity bất kỳ.

VD CEO mở quote 123 trong dashboard, ghi "lưu ý chốt khách trong tuần" →
comment lưu lại để app dept (baogia) hiển thị banner trên trang quote.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, BigInteger, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class CeoComment(Base):
    __tablename__ = "ceo_comments"
    __table_args__ = (
        Index("ix_ceo_comments_entity", "app", "entity_type", "entity_id"),
        Index("ix_ceo_comments_created", "created_at"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    app: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shared.users.id"))
    author_username: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
