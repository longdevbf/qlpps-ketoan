"""doanh_thu add ref_order_id (auto-create from muahang PO)

Adds a nullable `ref_order_id` column + index + partial unique index so that
auto-creating revenue from a purchase order is idempotent at the DB layer.

Revision ID: 0002_doanh_thu_ref_order
Revises: 0001_baseline_ketoan
Create Date: 2026-04-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_doanh_thu_ref_order"
down_revision: Union[str, None] = "0001_baseline_ketoan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "doanh_thu",
        sa.Column("ref_order_id", sa.String(length=32), nullable=True),
        schema="ketoan",
    )
    op.create_index(
        "ix_doanh_thu_ref_order",
        "doanh_thu",
        ["ref_order_id"],
        schema="ketoan",
    )
    # Partial unique idx — đảm bảo idempotent auto-create từ PO
    op.execute(
        "CREATE UNIQUE INDEX uq_doanh_thu_ref_order "
        "ON ketoan.doanh_thu (ref_order_id) WHERE ref_order_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ketoan.uq_doanh_thu_ref_order")
    op.drop_index("ix_doanh_thu_ref_order", table_name="doanh_thu", schema="ketoan")
    op.drop_column("doanh_thu", "ref_order_id", schema="ketoan")
