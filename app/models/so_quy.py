"""SoQuy — sổ quỹ giao dịch thu/chi (port từ `KT_SoQuy` + so_quy.json).

V1 fields:
    id ('GD-XXXXXXXX'), ngay, loai_gd ('Thu'/'Chi'), noi_dung, so_tien,
    tai_khoan ('Tiền Mặt'/'BIDV'/...), lien_quan, ghi_chu, created_by, created_at
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Numeric, DateTime, Date, Integer, Text, Index, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class SoQuy(Base):
    __tablename__ = "so_quy"
    __table_args__ = (
        Index("ix_sq_ngay", "ngay"),
        Index("ix_sq_loai", "loai"),
        Index("ix_sq_tk", "tai_khoan"),
        Index("ix_sq_ref_vc", "ref_vc"),
        Index("ix_sq_nv", "nhan_vien_id"),
        Index("ix_sq_ma_don", "ma_don"),
        # q14 (01/10/2026): phiếu lập tay theo nghiệp vụ — lọc / đếm 3388; chống bấm Lưu hai lần.
        Index("ix_sq_ma_dinh_khoan", "ma_dinh_khoan", postgresql_where=text("ma_dinh_khoan IS NOT NULL")),
        Index("ux_sq_nhap_tay_ref", "ref_id", unique=True,
              postgresql_where=text("lien_quan = 'nhap_tay' AND ref_id IS NOT NULL")),
        {"schema": "ketoan"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ngay: Mapped[date] = mapped_column(Date, nullable=False)
    loai: Mapped[str] = mapped_column(
        String(16), nullable=False
    )                                                                  # 'thu' | 'chi'
    so_tien: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), server_default="0", nullable=False
    )
    tai_khoan: Mapped[Optional[str]] = mapped_column(String(128))      # FK loose ketoan.tai_khoan_nh.ten_tk
    noi_dung: Mapped[Optional[str]] = mapped_column(Text)
    lien_quan: Mapped[Optional[str]] = mapped_column(String(128))      # module liên quan (chi_phi/doanh_thu/cong_no)
    # Phân loại dòng tiền = mã số báo cáo lưu chuyển tiền tệ (B03). Danh sách mã khai ở MỘT chỗ:
    # app/services/phan_loai_cf.py (không liệt kê lại ở đây). NULL = dòng cũ / bridge tự sinh chưa gắn mã.
    phan_loai_cf: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    ref_id: Mapped[Optional[str]] = mapped_column(String(128))         # snapshot id liên quan
    # Anh Quang 2026-06-06: Link giao dịch tới đơn báo giá (quote_number).
    # Cho phép nhiều giao dịch THU cùng ma_don → SUM = tổng đã cọc của đơn.
    ma_don: Mapped[Optional[str]] = mapped_column(String(64))
    # Auto-create từ saleadmin.vanchuyen.ma_vh — partial UNIQUE WHERE ref_vc IS NOT NULL
    ref_vc: Mapped[Optional[str]] = mapped_column(String(32))
    # Auto-create từ saleadmin.denghitt (CEO duyệt) — Format: 'DNTT-{id}'. Partial UNIQUE.
    ref_dntt: Mapped[Optional[str]] = mapped_column(String(32))
    # Auto-create từ SePay webhook — Format: 'SEPAY-{sepay_id}'. Partial UNIQUE chống double credit.
    ref_sepay: Mapped[Optional[str]] = mapped_column(String(64))
    mo_ta: Mapped[Optional[str]] = mapped_column(Text)
    ghi_chu: Mapped[Optional[str]] = mapped_column(Text)
    chung_tu_url: Mapped[Optional[str]] = mapped_column(Text)          # local upload URL `/api/uploads/so_quy_<id>/<file>`

    # Nhân viên (NV của Papasan thực hiện hoặc đối tác trong giao dịch)
    nhan_vien_id: Mapped[Optional[int]] = mapped_column(Integer)        # soft FK hcns.employees.id
    nhan_vien_ten: Mapped[Optional[str]] = mapped_column(String(255))   # cache tên hiển thị

    # Nghiệp vụ của phiếu lập tay (migration q14, 01/10/2026). Lưu KHOÁ nghiệp vụ, không lưu số tài khoản — cặp
    # Nợ/Có tra ở app/services/nghiep_vu_so_quy.py theo chế độ TT133/TT99. NULL = dòng cũ / cầu nối tự ghi.
    ma_dinh_khoan: Mapped[Optional[str]] = mapped_column(String(40))
    doi_tuong_loai: Mapped[Optional[str]] = mapped_column(String(20))   # 'khach' | 'ncc' | 'nv'
    doi_tuong_ma: Mapped[Optional[str]] = mapped_column(String(64))     # NCC: muahang.suppliers.id · NV: ma_nv
    doi_tuong_ten: Mapped[Optional[str]] = mapped_column(String(255))
    ky: Mapped[Optional[str]] = mapped_column(String(7))                # YYYY-MM: kỳ lương, bảo hiểm, thuế
    tk_doi_ung: Mapped[Optional[str]] = mapped_column(String(40))       # TÊN LOGIC — chỉ giai đoạn 2 ("Khác")
    # Ngày bên nhận THỰC NHẬN tiền (migration q17, 08/10/2026) — kế toán ghi ở hộp "Chi tiền và ghi sổ". Chỉ để
    # ghi nhận: ngày ghi sổ vẫn là `ngay` (chuyển khoản liên ngân hàng có thể nhận muộn hơn). Người nhận nằm ở
    # `doi_tuong_ten`. NULL = dòng cũ / chi từ client chưa có ô này.
    ngay_nhan: Mapped[Optional[date]] = mapped_column(Date)

    created_by: Mapped[Optional[str]] = mapped_column(String(64))
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
        return f"<SoQuy {self.id} {self.ngay} {self.loai} {self.so_tien}>"
