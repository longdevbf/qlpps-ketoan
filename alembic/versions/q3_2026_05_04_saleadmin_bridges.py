"""Bridges saleadmin → ketoan: phát sinh + đề nghị TT.

Thêm 3 cột ref + 3 partial UNIQUE để idempotent:
- chi_phi_phat_sinh.ref_phatsinh (saleadmin.phatsinh đã xử lý → ChiPhí)
- chi_phi_phat_sinh.ref_dntt     (saleadmin.denghitt duyệt → ChiPhí phải trả ĐVVC)
- so_quy.ref_dntt                 (saleadmin.denghitt duyệt → SoQuy chi)

Revision ID: q3_2026_05_04
Revises: q2_2026_04_29_quy_giao_dich
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "q3_2026_05_04"
down_revision: Union[str, None] = "q2_2026_04_29_quy_giao_dich"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # chi_phi_phat_sinh — 2 ref columns
    op.add_column(
        "chi_phi_phat_sinh",
        sa.Column("ref_phatsinh", sa.String(32), nullable=True),
        schema="ketoan",
    )
    op.add_column(
        "chi_phi_phat_sinh",
        sa.Column("ref_dntt", sa.String(32), nullable=True),
        schema="ketoan",
    )
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_chi_phi_ref_phatsinh
            ON ketoan.chi_phi_phat_sinh (ref_phatsinh)
            WHERE ref_phatsinh IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_chi_phi_ref_dntt
            ON ketoan.chi_phi_phat_sinh (ref_dntt)
            WHERE ref_dntt IS NOT NULL
    """)

    # so_quy — 1 ref column (ref_dntt)
    op.add_column(
        "so_quy",
        sa.Column("ref_dntt", sa.String(32), nullable=True),
        schema="ketoan",
    )
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_so_quy_ref_dntt
            ON ketoan.so_quy (ref_dntt)
            WHERE ref_dntt IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ketoan.ux_so_quy_ref_dntt")
    op.drop_column("so_quy", "ref_dntt", schema="ketoan")
    op.execute("DROP INDEX IF EXISTS ketoan.ux_chi_phi_ref_dntt")
    op.execute("DROP INDEX IF EXISTS ketoan.ux_chi_phi_ref_phatsinh")
    op.drop_column("chi_phi_phat_sinh", "ref_dntt", schema="ketoan")
    op.drop_column("chi_phi_phat_sinh", "ref_phatsinh", schema="ketoan")
