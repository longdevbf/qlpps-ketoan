"""MaiPreference — Memory/Preferences cho AI Mai.

Mai nhớ chỉ thị của user qua nhiều session. Ví dụ:
  - tone           : 'thân mật' | 'trang trọng'
  - focus_dept     : 'Kế Toán'
  - no_weekend_brief : 'yes'
  - report_format  : 'short'
"""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class MaiPreference(Base):
    __tablename__ = "mai_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_mai_preferences_user_key"),
        Index("ix_mai_preferences_user_id", "user_id"),
        Index("ix_mai_preferences_username", "username"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
