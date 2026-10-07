"""so_quy: thêm cột nghiệp vụ (mã định khoản), đối tượng, kỳ + 2 chỉ mục.

Đặc tả: Tài liệu/ban-giao-2026-09-30/cat-moc-30-09/spec_phieu_chon_ma_dinh_khoan.md mục 4.1.
Hộp Lập phiếu thu/chi ở Sổ quỹ đổi ô "Dòng tiền" thành ô "Việc gì?" (nghiệp vụ). Dòng sổ quỹ lưu KHOÁ
nghiệp vụ (bảng ở app/services/nghiep_vu_so_quy.py), không lưu số tài khoản — đổi TT133/TT99 không phải
sửa dữ liệu. Số migration q14: kế hoạch v2 đã giữ chỗ q9..q13 cho gói khác.

Sáu cột NULLABLE, không default (dòng cũ và dòng của các cầu nối tự ghi giữ NULL, KHÔNG backfill):
  - ma_dinh_khoan  varchar(40)   khoá nghiệp vụ, vd 'tra_ncc_ngoai_cong_no'
  - doi_tuong_loai varchar(20)   'khach' | 'ncc' | 'nv'   (cùng kiểu với journal_line ở q8)
  - doi_tuong_ma   varchar(64)
  - doi_tuong_ten  varchar(255)
  - ky             varchar(7)    YYYY-MM (kỳ lương, bảo hiểm, thuế)
  - tk_doi_ung     varchar(40)   TÊN LOGIC tài khoản đối ứng — chỉ dùng ở giai đoạn 2 (nghiệp vụ "Khác")
Hai chỉ mục:
  - ix_sq_ma_dinh_khoan  (ma_dinh_khoan) WHERE ma_dinh_khoan IS NOT NULL — lọc, đếm 3388, dựng lại sổ.
  - ux_sq_nhap_tay_ref   UNIQUE (ref_id) WHERE lien_quan='nhap_tay' AND ref_id IS NOT NULL — bấm Lưu hai lần
    chỉ ra một dòng. Trước khi chạy trên production: SELECT đếm dòng lien_quan='nhap_tay' trùng ref_id (dev 0 dòng).

An toàn: cột nullable không default → PostgreSQL chỉ đổi danh mục hệ thống, không ghi lại 815 dòng.
THỨ TỰ BẮT BUỘC khi lên production: chạy migration này TRƯỚC khi tạo lại bất kỳ container nào chạy code mới
(7 app dùng chung ORM SoQuy, `select(SoQuy)` liệt kê mọi cột).
Downgrade xoá 2 chỉ mục rồi 6 cột — MẤT thông tin nghiệp vụ của các phiếu đã lập (số tiền, ngày, quỹ,
dòng tiền vẫn còn nguyên).

Revision ID: q14_2026_10_01
Revises: q8_2026_10_01
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "q14_2026_10_01"
down_revision: Union[str, None] = "q8_2026_10_01"
branch_labels = None
depends_on = None

_COT = (
    ("ma_dinh_khoan", sa.String(40)),
    ("doi_tuong_loai", sa.String(20)),
    ("doi_tuong_ma", sa.String(64)),
    ("doi_tuong_ten", sa.String(255)),
    ("ky", sa.String(7)),
    ("tk_doi_ung", sa.String(40)),
)


def upgrade() -> None:
    for ten, kieu in _COT:
        op.add_column("so_quy", sa.Column(ten, kieu, nullable=True), schema="ketoan")
    op.create_index(
        "ix_sq_ma_dinh_khoan", "so_quy", ["ma_dinh_khoan"], schema="ketoan",
        postgresql_where=sa.text("ma_dinh_khoan IS NOT NULL"), if_not_exists=True,
    )
    op.create_index(
        "ux_sq_nhap_tay_ref", "so_quy", ["ref_id"], unique=True, schema="ketoan",
        postgresql_where=sa.text("lien_quan = 'nhap_tay' AND ref_id IS NOT NULL"), if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ux_sq_nhap_tay_ref", table_name="so_quy", schema="ketoan", if_exists=True)
    op.drop_index("ix_sq_ma_dinh_khoan", table_name="so_quy", schema="ketoan", if_exists=True)
    for ten, _kieu in reversed(_COT):
        op.drop_column("so_quy", ten, schema="ketoan")
