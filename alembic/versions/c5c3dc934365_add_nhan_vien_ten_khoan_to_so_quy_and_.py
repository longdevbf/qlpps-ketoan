"""add nhan_vien + ten_khoan to so_quy and chi_phi

- so_quy: nhan_vien_id (soft FK hcns.employees.id) + nhan_vien_ten cache
- chi_phi_co_dinh: ten_khoan VARCHAR(255) — tên khoản chi cụ thể
- chi_phi_phat_sinh: ten_khoan VARCHAR(255) — đồng bộ

Revision ID: c5c3dc934365
Revises: p2je_2026_04_28
Create Date: 2026-04-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5c3dc934365"
down_revision: Union[str, None] = "p2je_2026_04_28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # so_quy: thêm nhan_vien_id + cache tên
    op.add_column(
        "so_quy",
        sa.Column("nhan_vien_id", sa.Integer(), nullable=True),
        schema="ketoan",
    )
    op.add_column(
        "so_quy",
        sa.Column("nhan_vien_ten", sa.String(255), nullable=True),
        schema="ketoan",
    )
    op.create_index(
        "ix_sq_nv", "so_quy", ["nhan_vien_id"], schema="ketoan"
    )

    # chi_phi_co_dinh: tên khoản chi cụ thể
    op.add_column(
        "chi_phi_co_dinh",
        sa.Column("ten_khoan", sa.String(255), nullable=True),
        schema="ketoan",
    )

    # chi_phi_phat_sinh: tên khoản chi cụ thể (bonus)
    op.add_column(
        "chi_phi_phat_sinh",
        sa.Column("ten_khoan", sa.String(255), nullable=True),
        schema="ketoan",
    )


def downgrade() -> None:
    op.drop_column("chi_phi_phat_sinh", "ten_khoan", schema="ketoan")
    op.drop_column("chi_phi_co_dinh", "ten_khoan", schema="ketoan")
    op.drop_index("ix_sq_nv", "so_quy", schema="ketoan")
    op.drop_column("so_quy", "nhan_vien_ten", schema="ketoan")
    op.drop_column("so_quy", "nhan_vien_id", schema="ketoan")
