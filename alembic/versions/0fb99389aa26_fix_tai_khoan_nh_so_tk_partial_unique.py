"""fix tai_khoan_nh.so_tk partial unique

Trước đây UNIQUE(so_tk) full → khi nhiều TK không có số TK (vd 2 quỹ tiền mặt)
thì empty string '' và NULL bị conflict.

Fix: convert '' → NULL + đổi sang partial UNIQUE WHERE so_tk IS NOT NULL AND so_tk != ''.

Revision ID: 0fb99389aa26
Revises: c5c3dc934365
Create Date: 2026-04-28
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0fb99389aa26"
down_revision: Union[str, None] = "c5c3dc934365"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE ketoan.tai_khoan_nh SET so_tk = NULL WHERE so_tk = ''"
    )
    op.execute(
        "ALTER TABLE ketoan.tai_khoan_nh DROP CONSTRAINT IF EXISTS uq_tai_khoan_nh_so_tk"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tai_khoan_nh_so_tk "
        "ON ketoan.tai_khoan_nh (so_tk) WHERE so_tk IS NOT NULL AND so_tk <> ''"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ketoan.uq_tai_khoan_nh_so_tk"
    )
    op.execute(
        "ALTER TABLE ketoan.tai_khoan_nh "
        "ADD CONSTRAINT uq_tai_khoan_nh_so_tk UNIQUE (so_tk)"
    )
