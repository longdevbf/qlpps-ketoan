"""DeXuatChiTiet — phần bổ sung của một đề xuất, tách thành BẢNG RIÊNG.

Vì sao không thêm cột vào `shared.de_xuat` (người dùng chốt 12/09/2026: "thêm bảng
mới, không sửa bảng cũ"): bảng đó đang có dữ liệu thật và được 8 app đọc; thêm cột là
đụng vào đường đi của mọi app. Bảng này quan hệ 1-1 theo `de_xuat_id`, thiếu dòng thì
đề xuất vẫn chạy y như trước — đúng kiểu fail-soft mà hệ đang dùng.

Chứa đúng những thứ ảnh mẫu 12/09/2026 đòi mà bảng cũ không có chỗ:
  · `ma`                     mã hiển thị dạng DX260920-01 (bảng cũ chỉ có id số)
  · `nv_*`                   NHÂN VIÊN ĐƯỢC ĐỀ XUẤT — khác người gửi đơn; chụp lại
                             (snapshot) tên/phòng/chức vụ/ngày vào lúc gửi, để sau này
                             nhân viên đổi phòng thì đề xuất cũ vẫn đọc đúng bối cảnh
  · `ngay_ket_thuc_thu_viec` mốc mà `hcns.employees` không lưu
  · `ngay_hieu_luc`          ngày lên chính thức / ngày áp dụng dự kiến
  · `du_lieu`                JSONB cho phần riêng của từng loại (tăng lương: mức cũ/mới;
                             mua thiết bị: tên thiết bị, số lượng…) — thêm loại mới
                             không phải migrate bảng lần nữa
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class DeXuatChiTiet(Base):
    __tablename__ = "de_xuat_chi_tiet"
    __table_args__ = (
        Index("ix_de_xuat_ct_de_xuat_id", "de_xuat_id", unique=True),
        Index("ix_de_xuat_ct_ma", "ma"),
        Index("ix_de_xuat_ct_nv", "nv_username"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Không khai ForeignKey: `shared.de_xuat` do gói seed/ tạo bằng create_all, thứ tự
    # tạo bảng giữa hai model không đảm bảo. Xoá đề xuất thì router tự dọn dòng này.
    de_xuat_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ma: Mapped[Optional[str]] = mapped_column(String(32))

    nv_username: Mapped[Optional[str]] = mapped_column(String(64))
    nv_ma_nv: Mapped[Optional[str]] = mapped_column(String(32))
    nv_ho_ten: Mapped[Optional[str]] = mapped_column(String(255))
    nv_phong_ban: Mapped[Optional[str]] = mapped_column(String(128))
    nv_chuc_vu: Mapped[Optional[str]] = mapped_column(String(128))
    nv_ngay_vao: Mapped[Optional[date]] = mapped_column(Date)

    ngay_ket_thuc_thu_viec: Mapped[Optional[date]] = mapped_column(Date)
    ngay_hieu_luc: Mapped[Optional[date]] = mapped_column(Date)
    du_lieu: Mapped[Optional[dict]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
