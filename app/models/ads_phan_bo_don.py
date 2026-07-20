"""AdsPhanBoDon — phân bổ chi phí ads tháng X vào từng đơn báo giá đã chốt.

Phase 6A — Matching principle:
    - Marketing chi ads theo SP cụ thể trong tháng X.
    - Mỗi ads có 1 nhóm master ('Đồ Gỗ' | 'Đồ Mây' | 'Dự Án') hoặc "Khác"
      (san_pham không match 3 nhóm).
    - Pool ads "Khác" chia đều 3 nhóm (tổng ads không đổi).
    - Quotes chốt T X (duyet_status=approved + duyet_luc trong T X) sẽ
      "hút" ads theo % giá trị nhóm trong đơn so với tổng pool nhóm đó.
    - Khi VC sang `hoan_thanh` → row được flag thang_hoan_thanh = T thực
      hoàn thành → CP BH ghi nhận tháng đó.

Mỗi (thang_chi_ads, nhom_master, quote_number) → tối đa 1 dòng (UNIQUE
partial index nơi quote_number IS NOT NULL).

`loai_phan_bo`:
    - 'theo_nhom'           : pool ads gắn nhóm này có cả phần nguyên + chia đều Khác
    - 'redistribute_khac'   : (deprecated, dùng 'theo_nhom' kèm note) — chỉ ads từ Khác
    - 'no_match'            : pool có ads nhưng KHÔNG có đơn nào match nhóm trong tháng
                              → quote_number=NULL, ngay_chot=NULL, value/ty_le=NULL.
"""
from datetime import datetime, date as date_cls
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint, Date, DateTime, Index, Integer, Numeric, String,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class AdsPhanBoDon(Base):
    __tablename__ = "ads_phan_bo_don"
    __table_args__ = (
        CheckConstraint(
            "nhom_master IN ('Đồ Gỗ', 'Đồ Mây', 'Dự Án')",
            name="ck_apb_nhom",
        ),
        CheckConstraint(
            "loai_phan_bo IN ('theo_nhom', 'redistribute_khac', 'no_match')",
            name="ck_apb_loai",
        ),
        # Partial UNIQUE index `uq_apb_thang_nhom_quote` (WHERE quote_number IS NOT NULL)
        # tạo qua raw SQL trong migration p6a_ — không khai báo ở đây để tránh
        # Alembic autogenerate mismatch.
        Index("ix_apb_thang_chi", "thang_chi_ads"),
        Index("ix_apb_thang_ht", "thang_hoan_thanh"),
        Index("ix_apb_quote", "quote_number"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    thang_chi_ads: Mapped[str] = mapped_column(String(7), nullable=False)
    nhom_master: Mapped[str] = mapped_column(String(32), nullable=False)

    # Quote chốt được phân bổ ads (NULL nếu pool có ads nhưng 0 đơn match → no_match)
    quote_number: Mapped[Optional[str]] = mapped_column(String(64))
    ngay_chot: Mapped[Optional[date_cls]] = mapped_column(Date)

    # Giá trị phần nhóm này trong đơn (SUM line_value items match nhóm)
    value_nhom_trong_don: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    # % của đơn trong pool nhóm đó (0..1)
    ty_le_pool: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 4))

    so_tien_phan_bo: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)

    loai_phan_bo: Mapped[str] = mapped_column(String(20), nullable=False)

    # Đồng bộ với saleadmin.vanchuyen.trang_thai khi VC sang hoan_thanh
    vc_status: Mapped[Optional[str]] = mapped_column(String(20))
    thang_hoan_thanh: Mapped[Optional[str]] = mapped_column(String(7))

    # Snapshot CPA (chi phí / số đơn nhóm) tại thời điểm phân bổ
    cpa_nhom_snapshot: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<AdsPhanBoDon {self.thang_chi_ads}/{self.nhom_master} "
            f"q={self.quote_number} st={self.so_tien_phan_bo}>"
        )
