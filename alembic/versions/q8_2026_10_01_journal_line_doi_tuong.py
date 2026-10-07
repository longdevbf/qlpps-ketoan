"""journal_line: thêm cột đối tượng (khách/NCC/nhân viên) và mã đơn + chỉ mục (account_code, doi_tuong_ma).

Bước 1 "nền móng sổ cái" của kế hoạch chuyển Kế toán sang tự định khoản (mục N06,
thu_tu_trien_khai.md, 01/10/2026): hiện `journal_line` chỉ có ref_table/ref_id (số nguyên) nên
không dựng được sổ chi tiết 131/331/141 theo từng khách/NCC/nhân viên, và không tra được
"bút toán nào của đơn NV26001-26-00110". Chi tiết đối tượng chỉ có ở số dư đầu kỳ
(`ketoan.so_du_dau_ky_doi_tuong`).

Thêm 4 cột NULLABLE (bút toán cũ để NULL, KHÔNG backfill — số dư đầu kỳ đã gánh quá khứ):
  - doi_tuong_loai  varchar(20)  'khach' | 'ncc' | 'nv'
  - doi_tuong_ma    varchar(64)
  - doi_tuong_ten   varchar(255)
  - ma_don          varchar(64)
và chỉ mục `ix_jl_account_doi_tuong (account_code, doi_tuong_ma)` cho sổ chi tiết.

KHÔNG tạo UNIQUE partial chống trùng bút toán theo (source_type, source_id) ở đây: mốc áp dụng đã đổi
từ 01/10 sang 01/05/2026 nên điều kiện `ngay >= ...` của khoá phải chốt lại cùng Bước 2 (xem báo cáo).
KHÔNG tạo lại các chỉ mục uq_sq_lienquan_refid / ux_so_quy_ref_sepay (mục N11) — việc khác.

An toàn: cột nullable, không server_default → PostgreSQL 16 chỉ đổi catalog, không ghi lại bảng.
Downgrade xoá chỉ mục rồi 4 cột — MẤT dữ liệu đối tượng/mã đơn đã ghi sau khi upgrade (bút toán và
số tiền không đổi).

Revision ID: q8_2026_10_01
Revises: q7_2026_09_30
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "q8_2026_10_01"
down_revision: Union[str, None] = "q7_2026_09_30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "journal_line", sa.Column("doi_tuong_loai", sa.String(20), nullable=True), schema="ketoan",
    )
    op.add_column(
        "journal_line", sa.Column("doi_tuong_ma", sa.String(64), nullable=True), schema="ketoan",
    )
    op.add_column(
        "journal_line", sa.Column("doi_tuong_ten", sa.String(255), nullable=True), schema="ketoan",
    )
    op.add_column(
        "journal_line", sa.Column("ma_don", sa.String(64), nullable=True), schema="ketoan",
    )
    op.create_index(
        "ix_jl_account_doi_tuong", "journal_line", ["account_code", "doi_tuong_ma"],
        schema="ketoan", if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_jl_account_doi_tuong", table_name="journal_line", schema="ketoan", if_exists=True,
    )
    op.drop_column("journal_line", "ma_don", schema="ketoan")
    op.drop_column("journal_line", "doi_tuong_ten", schema="ketoan")
    op.drop_column("journal_line", "doi_tuong_ma", schema="ketoan")
    op.drop_column("journal_line", "doi_tuong_loai", schema="ketoan")
