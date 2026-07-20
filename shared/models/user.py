from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, DateTime, ARRAY, Index
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base
from shared.db.base import TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_role", "role"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    # apps NV được phép truy cập: ['baogia','marketing','muahang']
    apps: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # On-duty toggle — KD/manager bật/tắt để cho/không cho MKT giao lead.
    # Default TRUE (mới tạo = đang trực).
    is_on_duty: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False,
    )
    phone: Mapped[Optional[str]] = mapped_column(String(32))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512))
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<User {self.username} role={self.role}>"
