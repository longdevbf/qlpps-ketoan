"""PhanBo242 — thông tin kế toán bổ sung cho một khoản chi phí chờ phân bổ (TK 242).

Bản thân khoản phân bổ là 1 dòng `ketoan.chi_phi_co_dinh` có `so_thang_phan_bo > 1`
(đó là nguồn mà báo cáo KQKD `pl_calculator` đang phân bổ vào chi phí hằng tháng).
Bảng này chỉ lưu phần `chi_phi_co_dinh` không có: loại (trả trước / CCDC), TK chi
phí, TK nguồn, bộ phận và bút toán ghi nhận Nợ 242 — cho các khoản thêm từ màn
/ketoan/phan-bo. Khoản nhập từ màn Chi phí cố định cũ không có dòng ở đây.

Bảng tạo bằng DDL idempotent trong `services/thue_phan_bo_schema.py`.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class PhanBo242(Base):
    __tablename__ = "phan_bo_242"
    __table_args__ = ({"schema": "ketoan"},)

    cpcd_id: Mapped[int] = mapped_column(
        ForeignKey("ketoan.chi_phi_co_dinh.id", ondelete="CASCADE"), primary_key=True,
    )
    loai: Mapped[str] = mapped_column(String(10), nullable=False)        # 'tra_truoc' | 'ccdc'
    tk_cp: Mapped[str] = mapped_column(String(10), nullable=False)       # 641 | 642
    tk_nguon: Mapped[str] = mapped_column(String(10), nullable=False)    # 111 | 112 | 331
    bo_phan: Mapped[Optional[str]] = mapped_column(String(60))
    je_ghi_nhan_id: Mapped[Optional[int]] = mapped_column(Integer)       # journal_entry Nợ 242
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
