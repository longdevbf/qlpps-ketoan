"""Tài liệu / Văn bản — hai bảng PHỤ cho `hcns.documents`.

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

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
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
