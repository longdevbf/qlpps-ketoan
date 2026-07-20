"""Add bridge fields to chi_phi_phat_sinh:
- ref_ads_thang_kenh: idempotent key for ADS marketing → chi_phi (1 row/tháng/kênh)
- ref_payroll_thang_pb: idempotent key for HCNS lương → chi_phi (1 row/tháng/phòng ban)

Partial UNIQUE indexes WHERE NOT NULL → cho phép upsert idempotent mà
KHÔNG ràng buộc với rows manual (NULL).

Revision ID: 0007_chi_phi_bridges
Revises: 0006_khoan_vay
Create Date: 2026-04-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_chi_phi_bridges"
down_revision: Union[str, None] = "0006_khoan_vay"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chi_phi_phat_sinh",
        sa.Column("ref_ads_thang_kenh", sa.String(64), nullable=True),
        schema="ketoan",
    )
    op.add_column(
        "chi_phi_phat_sinh",
        sa.Column("ref_payroll_thang_pb", sa.String(96), nullable=True),
        schema="ketoan",
    )
    op.create_index(
        "ix_cpps_ref_ads",
        "chi_phi_phat_sinh", ["ref_ads_thang_kenh"],
        schema="ketoan",
    )
    op.create_index(
        "ix_cpps_ref_payroll",
        "chi_phi_phat_sinh", ["ref_payroll_thang_pb"],
        schema="ketoan",
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_cpps_ref_ads ON ketoan.chi_phi_phat_sinh(ref_ads_thang_kenh) "
        "WHERE ref_ads_thang_kenh IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_cpps_ref_payroll ON ketoan.chi_phi_phat_sinh(ref_payroll_thang_pb) "
        "WHERE ref_payroll_thang_pb IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ketoan.uq_cpps_ref_payroll")
    op.execute("DROP INDEX IF EXISTS ketoan.uq_cpps_ref_ads")
    op.drop_index("ix_cpps_ref_payroll", table_name="chi_phi_phat_sinh", schema="ketoan")
    op.drop_index("ix_cpps_ref_ads", table_name="chi_phi_phat_sinh", schema="ketoan")
    op.drop_column("chi_phi_phat_sinh", "ref_payroll_thang_pb", schema="ketoan")
    op.drop_column("chi_phi_phat_sinh", "ref_ads_thang_kenh", schema="ketoan")
