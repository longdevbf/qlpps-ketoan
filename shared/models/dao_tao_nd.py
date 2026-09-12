"""Thư viện nội dung đào tạo — hai bảng MỚI (12/09/2026).

Khác `marketing.dao_tao_sessions` (buổi đào tạo: tên, ngày, giảng viên, phòng ban, tệp)
đang chạy ở 6 app: đây là THƯ VIỆN NỘI DUNG theo ảnh mẫu người dùng gửi — video, tài
liệu, đường dẫn, có chủ đề, thẻ, ảnh đại diện, lượt xem, lượt thích, đánh dấu. Bảng cũ
không có chỗ cho một thứ nào trong số đó nên tách bảng mới thay vì nhồi thêm cột.

Đặt ở schema `shared` vì 8 app cùng đọc và cùng ghi (bảng cũ nằm ở schema `marketing`,
7 app kia phải import model chéo mới dùng được).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class DaoTaoNoiDung(Base):
    """Một nội dung trong thư viện: video, tài liệu hoặc đường dẫn."""

    __tablename__ = "dao_tao_noi_dung"
    __table_args__ = (
        Index("ix_dtnd_chu_de", "chu_de"),
        Index("ix_dtnd_loai", "loai_nd"),
        Index("ix_dtnd_pham_vi", "pham_vi", "phong_ban"),
        Index("ix_dtnd_created", "created_at"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tieu_de: Mapped[str] = mapped_column(String(255), nullable=False)
    mo_ta: Mapped[Optional[str]] = mapped_column(Text)
    loai_nd: Mapped[str] = mapped_column(String(16), nullable=False)      # video | tai_lieu | link
    chu_de: Mapped[Optional[str]] = mapped_column(String(64))
    pham_vi: Mapped[str] = mapped_column(String(16), nullable=False, server_default="cong_ty")
    phong_ban: Mapped[Optional[str]] = mapped_column(String(128))         # dùng khi pham_vi='phong_ban'

    # Tệp lưu ở `<UPLOAD_DIR>/dao_tao/<id>/<uuid>.<ext>`; `link_url` dùng cho loại 'link'.
    ten_tep: Mapped[Optional[str]] = mapped_column(String(255))
    duong_dan_tep: Mapped[Optional[str]] = mapped_column(String(512))
    link_url: Mapped[Optional[str]] = mapped_column(String(512))
    anh_dai_dien: Mapped[Optional[str]] = mapped_column(String(512))
    kich_thuoc: Mapped[Optional[int]] = mapped_column(Integer)            # byte
    thoi_luong: Mapped[Optional[int]] = mapped_column(Integer)            # giây, chỉ video

    the: Mapped[Optional[list]] = mapped_column(JSONB)                    # danh sách thẻ (tag)
    lien_quan: Mapped[Optional[list]] = mapped_column(JSONB)              # id nội dung liên quan

    nguoi_chia_se: Mapped[Optional[str]] = mapped_column(String(64))      # username
    nguoi_chia_se_ten: Mapped[Optional[str]] = mapped_column(String(255))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DaoTaoTuongTac(Base):
    """Một dòng = một lần xem, một lượt thích hoặc một lần đánh dấu.

    Thích và đánh dấu là BẬT/TẮT nên router tự xoá dòng khi bỏ; xem thì cộng dồn.
    """

    __tablename__ = "dao_tao_tuong_tac"
    __table_args__ = (
        Index("ix_dttt_nd", "noi_dung_id"),
        Index("ix_dttt_user", "username", "hanh_dong"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    noi_dung_id: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64))
    hanh_dong: Mapped[str] = mapped_column(String(12), nullable=False)    # xem | thich | danh_dau
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
