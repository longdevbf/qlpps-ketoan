"""DeXuatChamCong — đề xuất chấm công lại (giờ đến thực tế ≠ giờ trên hệ thống).

`phi` = số tiền người gửi đề xuất (mức tối thiểu do HCNS đặt, càng cao càng được xếp lên đầu hàng
duyệt). Tiền CHỈ bị trừ khi đề xuất được duyệt xong, và do CEO quyết định lúc duyệt cuối:
`phi_tru` = số tiền thực trừ vào Tối ưu KD (NULL = chưa quyết, 0 = không trừ).
Duyệt 2 cấp: Quản lý phòng (`cho_quan_ly`) → CEO (`cho_ceo`) → `da_duyet`.
"""
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, Index, Integer, Numeric, String, Text, Time, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base

TRANG_THAI_CHO_QUAN_LY = "cho_quan_ly"
TRANG_THAI_CHO_CEO = "cho_ceo"
TRANG_THAI_DA_DUYET = "da_duyet"
TRANG_THAI_TU_CHOI = "tu_choi"

# Đề xuất còn hiệu lực: chiếm "chỗ" của ngày đó, không cho gửi trùng.
TRANG_THAI_CON_HIEU_LUC = (TRANG_THAI_CHO_QUAN_LY, TRANG_THAI_CHO_CEO, TRANG_THAI_DA_DUYET)


class DeXuatChamCong(Base):
    __tablename__ = "de_xuat_cham_cong"
    __table_args__ = (
        Index("ix_de_xuat_cham_cong_username", "username"),
        Index("ix_de_xuat_cham_cong_trang_thai", "trang_thai"),
        Index("ix_de_xuat_cham_cong_ma_nv_created", "ma_nv", "created_at"),
        # Mỗi ngày chỉ một đề xuất còn hiệu lực (bị từ chối thì được gửi lại) — chặn bấm đúp bị tính phí 2 lần.
        Index("uq_de_xuat_cham_cong_hieu_luc", "username", "ngay", unique=True,
              postgresql_where=text("trang_thai <> 'tu_choi'")),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    ma_nv: Mapped[str] = mapped_column(String(16), nullable=False)
    ho_ten: Mapped[str] = mapped_column(String(128), nullable=False)
    phong_ban: Mapped[Optional[str]] = mapped_column(String(128))
    app_name: Mapped[str] = mapped_column(String(32), nullable=False)

    ngay: Mapped[date] = mapped_column(Date, nullable=False)
    gio_thuc_te: Mapped[time] = mapped_column(Time, nullable=False)
    gio_he_thong: Mapped[Optional[time]] = mapped_column(Time)  # NULL = hôm đó chưa có bản ghi chấm công
    gio_truoc_khi_sua: Mapped[Optional[time]] = mapped_column(Time)  # giờ vào bị ghi đè lúc duyệt xong
    ly_do: Mapped[str] = mapped_column(Text, nullable=False)

    phi: Mapped[Decimal] = mapped_column(Numeric(15, 0), nullable=False, server_default="0")  # số tiền người gửi đề xuất
    phi_tru: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 0))  # số tiền CEO quyết định trừ (0 = không trừ)

    trang_thai: Mapped[str] = mapped_column(String(16), nullable=False, server_default=TRANG_THAI_CHO_QUAN_LY)
    tu_choi_boi: Mapped[Optional[str]] = mapped_column(String(16))  # 'quan_ly' | 'ceo'

    quan_ly_duyet: Mapped[Optional[str]] = mapped_column(String(64))
    ho_ten_quan_ly: Mapped[Optional[str]] = mapped_column(String(128))
    quan_ly_luc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    quan_ly_nhan_xet: Mapped[Optional[str]] = mapped_column(Text)

    ceo_duyet: Mapped[Optional[str]] = mapped_column(String(64))
    ho_ten_ceo: Mapped[Optional[str]] = mapped_column(String(128))
    ceo_luc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ceo_nhan_xet: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
