"""CaiDatHeThong — chính sách kế toán (kỳ, giá xuất kho, khấu hao, khai thuế)
+ quy tắc đánh số chứng từ. Bảng singleton: đúng 1 dòng, id=1.

Đọc/sửa qua tab "Chính sách" + "Đánh số chứng từ" của màn Cài đặt Kế toán
(GET /api/cai-dat, PUT /api/cai-dat/ke_toan | /api/cai-dat/danh_so).

Lưu ý (anh Quang 2026-09-25): `danh_so` mới CHỈ LÀ CẤU HÌNH LƯU TRỮ — số chứng
từ THẬT hiện tại (`ma_but_toan`) vẫn do `services/journal.py:next_ma_but_toan()`
tự sinh cứng "BT-{năm}-{stt:04d}", CHƯA đọc bảng này. Nối 2 bên là việc của một
đợt sau (đổi next_ma_but_toan để tra `danh_so` theo `source_type`/loại chứng từ).
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Date, DateTime, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class CaiDatHeThong(Base):
    __tablename__ = "cai_dat_he_thong"
    __table_args__ = (
        CheckConstraint("id = 1", name="cai_dat_he_thong_singleton_ck"),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)

    # ── Chế độ & kỳ kế toán ──
    che_do: Mapped[str] = mapped_column(String(20), nullable=False, server_default="tt99")
    nam_tc_bat_dau: Mapped[str] = mapped_column(String(2), nullable=False, server_default="01")
    tien_te: Mapped[str] = mapped_column(String(10), nullable=False, server_default="VND")
    ngay_bat_dau_dung: Mapped[Optional[date]] = mapped_column(Date)

    # ── Chính sách kế toán ──
    gia_xuat_kho: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="binh_quan_cuoi_ky",
    )
    khau_hao: Mapped[str] = mapped_column(String(30), nullable=False, server_default="duong_thang")
    ky_ke_khai_thue: Mapped[str] = mapped_column(String(10), nullable=False, server_default="quy")

    # ── Đánh số chứng từ: [{ma, ten, tien_to, do_dai, lam_lai}, …] ──
    danh_so: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")

    updated_by: Mapped[Optional[str]] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<CaiDatHeThong che_do={self.che_do} nam_tc={self.nam_tc_bat_dau}>"
