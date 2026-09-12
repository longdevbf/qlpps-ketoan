"""Tài liệu / Văn bản — ba bảng PHỤ cho `hcns.documents`.

Bảng gốc `hcns.documents` (10 cột, do app HCNS sở hữu) chỉ có: loại, tiêu đề, nội dung,
file, ngày ban hành, phòng ban áp dụng, người tạo, số hiệu. Ảnh mẫu 12/09/2026 còn đòi
danh mục chuẩn, cơ quan ban hành, cờ nổi bật, lượt xem, lượt tải, số người truy cập.

Người dùng chốt 12/09/2026: "thêm bảng mới, không sửa bảng cũ" — nên phần bổ sung nằm ở
schema `shared` (8 app đều ghi được), còn `hcns.documents` giữ nguyên và vẫn là nguồn sự
thật cho nội dung văn bản. Thiếu dòng phụ thì màn vẫn chạy: danh mục suy từ `loai`, số
đếm bằng 0.

Vì sao lưu TỪNG LƯỢT thay vì một cột đếm: ảnh mẫu có cả "Lượt xem", "Lượt tải" và "Người
truy cập" — con số thứ ba là số NGƯỜI khác nhau, không cộng dồn được từ một biến đếm.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class TaiLieuMeta(Base):
    """Phần mô tả thêm của một văn bản — 1-1 với `hcns.documents.id`."""

    __tablename__ = "tai_lieu_meta"
    __table_args__ = (
        Index("ix_tl_meta_doc", "doc_id", unique=True),
        Index("ix_tl_meta_danh_muc", "danh_muc"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Một trong 7 danh mục chuẩn ở ảnh mẫu; rỗng thì màn tự suy từ `documents.loai`.
    danh_muc: Mapped[Optional[str]] = mapped_column(String(64))
    co_quan_ban_hanh: Mapped[Optional[str]] = mapped_column(String(128))
    noi_bat: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TaiLieuLuot(Base):
    """Một dòng = một lần MỞ hoặc TẢI một văn bản. Nguồn của cả 3 con số thống kê."""

    __tablename__ = "tai_lieu_luot"
    __table_args__ = (
        Index("ix_tl_luot_doc", "doc_id"),
        Index("ix_tl_luot_user", "username"),
        Index("ix_tl_luot_at", "at"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64))
    hanh_dong: Mapped[str] = mapped_column(String(8), nullable=False)  # xem | tai
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaiLieuTep(Base):
    """Tài liệu do người dùng tải lên TỪ MÀN CHUNG — nguồn thứ hai, đứng cạnh `hcns.documents`.

    Vì sao cần: `hcns.documents` là schema của app HCNS, 7 app kia chỉ được đọc, nên nút
    "Tải lên tài liệu" trước đây phải ẩn ở 7 app. Người dùng chốt 12/09/2026 là cho cả 8
    app tải lên được, vẫn theo hướng "thêm bảng mới, không sửa bảng cũ".

    Danh sách trên màn gộp hai nguồn. Để id không đụng nhau, dòng của bảng này ra ngoài
    với id ÂM (`-id`) — cùng cách `shared/routers/calendar.py` đặt id âm cho sự kiện ảo.
    Nhờ vậy `tai_lieu_meta` / `tai_lieu_luot` dùng chung được, không phải nhân đôi cột.
    """

    __tablename__ = "tai_lieu_tep"
    __table_args__ = (
        Index("ix_tl_tep_danh_muc", "danh_muc"),
        Index("ix_tl_tep_created", "created_at"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ten: Mapped[str] = mapped_column(String(255), nullable=False)
    so_hieu: Mapped[Optional[str]] = mapped_column(String(64))
    danh_muc: Mapped[str] = mapped_column(String(64), nullable=False)
    ngay_ban_hanh: Mapped[Optional[Date]] = mapped_column(Date)
    co_quan_ban_hanh: Mapped[Optional[str]] = mapped_column(String(128))
    # Rỗng = áp dụng toàn công ty. Cùng kiểu với `hcns.documents.ap_dung_phong_ban`.
    ap_dung_phong_ban: Mapped[Optional[list]] = mapped_column(JSONB)
    mo_ta: Mapped[Optional[str]] = mapped_column(Text)
    ten_tep: Mapped[Optional[str]] = mapped_column(String(255))
    duong_dan_tep: Mapped[Optional[str]] = mapped_column(Text)
    kich_thuoc: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    # App nơi bấm nút tải lên — chỉ để truy vết, không dùng để lọc.
    app: Mapped[Optional[str]] = mapped_column(String(32))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
