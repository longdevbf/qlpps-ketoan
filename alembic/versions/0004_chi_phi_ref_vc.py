"""chi_phi_phat_sinh + so_quy add ref_vc (auto-create from saleadmin VanChuyen)

Adds nullable `ref_vc` columns + partial UNIQUE indexes WHERE ref_vc IS NOT NULL
on `ketoan.chi_phi_phat_sinh` and `ketoan.so_quy`. Bridge SaleAdmin VC
'Đã giao' / 'Hoàn Thành' → tự sinh entry chi phí VC + thu sổ quỹ COD,
idempotent ở DB layer.

Pattern theo `0002_doanh_thu_ref_order` (Task #3).

NOTE: Spec ban đầu yêu cầu revision="0003_chi_phi_ref_vc" nhưng `0003_add_breakdown_tables`
đã tồn tại trước. Chain sau (0004) để giữ history tuyến tính, tránh branch heads.

Revision ID: 0004_chi_phi_ref_vc
Revises: 0003_add_breakdown_tables
Create Date: 2026-04-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_chi_phi_ref_vc"
down_revision: Union[str, None] = "0003_add_breakdown_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----------------- chi_phi_phat_sinh.ref_vc -----------------
    op.add_column(
        "chi_phi_phat_sinh",
        sa.Column("ref_vc", sa.String(length=32), nullable=True),
        schema="ketoan",
    )
    op.create_index(
        "ix_cpps_ref_vc",
        "chi_phi_phat_sinh",
        ["ref_vc"],
        schema="ketoan",
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_cpps_ref_vc "
        "ON ketoan.chi_phi_phat_sinh (ref_vc) WHERE ref_vc IS NOT NULL"
    )

    # ----------------- so_quy.ref_vc -----------------
    op.add_column(
        "so_quy",
        sa.Column("ref_vc", sa.String(length=32), nullable=True),
        schema="ketoan",
    )
    op.create_index(
        "ix_sq_ref_vc",
        "so_quy",
        ["ref_vc"],
        schema="ketoan",
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_sq_ref_vc "
        "ON ketoan.so_quy (ref_vc) WHERE ref_vc IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ketoan.uq_sq_ref_vc")
    op.drop_index("ix_sq_ref_vc", table_name="so_quy", schema="ketoan")
    op.drop_column("so_quy", "ref_vc", schema="ketoan")

    op.execute("DROP INDEX IF EXISTS ketoan.uq_cpps_ref_vc")
    op.drop_index("ix_cpps_ref_vc", table_name="chi_phi_phat_sinh", schema="ketoan")
    op.drop_column("chi_phi_phat_sinh", "ref_vc", schema="ketoan")
