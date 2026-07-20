"""ExpenseRequest — đề xuất chi cross-app (3-step: manager → kế toán → CEO)."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class ExpenseRequest(Base):
    __tablename__ = "expense_requests"
    __table_args__ = (
        Index("ix_expense_requests_username", "username"),
        Index("ix_expense_requests_trang_thai", "trang_thai"),
        Index("ix_expense_requests_ngay", "ngay_de_xuat"),
        Index("ix_expense_requests_approval_level", "approval_level"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    ho_ten: Mapped[str] = mapped_column(String(128), nullable=False)
    phong_ban: Mapped[Optional[str]] = mapped_column(String(128))
    app_name: Mapped[str] = mapped_column(String(32), nullable=False)

    tieu_de: Mapped[str] = mapped_column(String(256), nullable=False)
    loai_chi: Mapped[str] = mapped_column(String(64), nullable=False)
    # loai_chi: di_chuyen, van_phong, tiep_thi, dao_tao, khach_hang, khac

    so_tien: Mapped[Decimal] = mapped_column(Numeric(15, 0), nullable=False)
    ngay_de_xuat: Mapped[date] = mapped_column(Date, nullable=False)
    han_thanh_toan: Mapped[Optional[date]] = mapped_column(Date)
    muc_dich: Mapped[str] = mapped_column(Text, nullable=False)
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    chung_tu_url: Mapped[Optional[str]] = mapped_column(Text)
    # Đa file: list URL chứng từ. Backward-compat với chung_tu_url (= phần tử
    # đầu khi có). API mới append vào list, legacy field giữ cho FE cũ.
    chung_tu_urls: Mapped[list] = mapped_column(
        JSONB, server_default="[]", nullable=False, default=list
    )

    trang_thai: Mapped[str] = mapped_column(String(32), server_default="cho_duyet")
    # cho_duyet (đang đi qua các cấp) | da_duyet (xong CEO) | tu_choi

    # 3-step workflow
    approval_level: Mapped[str] = mapped_column(
        String(16), server_default="manager", nullable=False
    )
    # manager → ketoan → ceo → done. Reject ở bất kỳ cấp nào → 'rejected'.
    approval_history: Mapped[list] = mapped_column(
        JSONB, server_default="[]", nullable=False, default=list
    )
    # JSONB array of {level, username, ho_ten, action approve|reject, comment, at}

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
