"""LeaveRequest — đơn xin nghỉ cross-app."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    __table_args__ = (
        Index("ix_leave_requests_username", "username"),
        Index("ix_leave_requests_trang_thai", "trang_thai"),
        Index("ix_leave_requests_ngay", "ngay_bat_dau"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    ho_ten: Mapped[str] = mapped_column(String(128), nullable=False)
    phong_ban: Mapped[Optional[str]] = mapped_column(String(128))
    app_name: Mapped[str] = mapped_column(String(32), nullable=False)

    loai_nghi: Mapped[str] = mapped_column(String(64), nullable=False)
    # loai_nghi values: nghi_phep, nghi_bu, nghi_khong_luong, nghi_om, viec_rieng, nghi_le

    ngay_bat_dau: Mapped[date] = mapped_column(Date, nullable=False)
    ngay_ket_thuc: Mapped[date] = mapped_column(Date, nullable=False)
    buoi: Mapped[str] = mapped_column(String(16), server_default="ca_ngay")
    # buoi: ca_ngay, sang, chieu
    so_ngay: Mapped[Decimal] = mapped_column(Numeric(4, 1), server_default="1")

    ly_do: Mapped[str] = mapped_column(Text, nullable=False)
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)

    trang_thai: Mapped[str] = mapped_column(String(32), server_default="cho_duyet")
    # cho_duyet, da_duyet, tu_choi

    nguoi_duyet: Mapped[Optional[str]] = mapped_column(String(64))
    ho_ten_nguoi_duyet: Mapped[Optional[str]] = mapped_column(String(128))
    nhan_xet_duyet: Mapped[Optional[str]] = mapped_column(Text)
    ngay_duyet: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
