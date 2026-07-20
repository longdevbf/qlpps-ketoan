"""doanh_thu + cong_no + so_quy add chung_tu_url (local file upload)

Adds nullable `chung_tu_url` TEXT columns on `ketoan.doanh_thu`,
`ketoan.cong_no` and `ketoan.so_quy` to lưu URL chứng từ upload local
(serve qua `/api/uploads/{scope}/{filename}`).

Pattern: file upload local-only (helper `shared.utils.uploads.save_upload`),
KHÔNG dùng Drive — URL trả về dạng `/api/uploads/<scope>/<filename>`.

Revision ID: 0005_add_doanh_thu_chung_tu
Revises: 0004_chi_phi_ref_vc
Create Date: 2026-04-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_add_doanh_thu_chung_tu"
down_revision: Union[str, None] = "0004_chi_phi_ref_vc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "doanh_thu",
        sa.Column("chung_tu_url", sa.Text(), nullable=True),
        schema="ketoan",
    )
    op.add_column(
        "cong_no",
        sa.Column("chung_tu_url", sa.Text(), nullable=True),
        schema="ketoan",
    )
    op.add_column(
        "so_quy",
        sa.Column("chung_tu_url", sa.Text(), nullable=True),
        schema="ketoan",
    )


def downgrade() -> None:
    op.drop_column("so_quy", "chung_tu_url", schema="ketoan")
    op.drop_column("cong_no", "chung_tu_url", schema="ketoan")
    op.drop_column("doanh_thu", "chung_tu_url", schema="ketoan")
