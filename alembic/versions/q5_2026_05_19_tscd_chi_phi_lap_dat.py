"""Add column ketoan.tai_san_co_dinh.chi_phi_lap_dat (tracking).

Cột tracking phần chi phí lắp đặt nằm trong nguyen_gia. Không ảnh hưởng khấu hao
(vẫn dùng nguyen_gia làm cơ sở). Default 0.

Revision ID: q5_2026_05_19
Revises: q4_2026_05_07
"""
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "q5_2026_05_19"
down_revision: Union[str, None] = "q4_2026_05_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tai_san_co_dinh",
        sa.Column(
            "chi_phi_lap_dat",
            sa.Numeric(15, 2),
            nullable=False,
            server_default="0",
        ),
        schema="ketoan",
    )


def downgrade() -> None:
    op.drop_column("tai_san_co_dinh", "chi_phi_lap_dat", schema="ketoan")
