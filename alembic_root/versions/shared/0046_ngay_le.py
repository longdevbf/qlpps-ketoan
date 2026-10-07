"""Ngày lễ hưởng nguyên lương (hcns.ngay_le) — payroll không phạt + tính đủ công.

Revision ID: 0046_ngay_le
Revises: 0045_kho_reservation
Create Date: 2026-08-26
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0046_ngay_le"
down_revision: Union[str, None] = "0045_kho_reservation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ngay_le",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ngay", sa.Date(), nullable=False),
        sa.Column("ten", sa.String(length=255), nullable=False),
        sa.Column(
            "loai", sa.String(length=8), nullable=False,
            server_default=sa.text("'full'"),
        ),
        sa.Column(
            "active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ngay", name="uq_ngay_le_ngay"),
        schema="hcns",
    )


def downgrade() -> None:
    op.drop_table("ngay_le", schema="hcns")
