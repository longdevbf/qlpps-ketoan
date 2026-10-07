"""shared.product_addons: thêm cột cach_tinh String(16) — 3 modes.

Thay flag boolean tinh_per_m2 (chỉ 2 mode) bằng string enum 3 mode:
- 'flat'        — cộng thẳng (mặc định)
- 'per_m2'      — giá × R × C (m²)
- 'per_m_dai'   — giá × R (m dài)

Giữ tinh_per_m2 cho backward compat (sẽ drop ở migration sau).
Backfill cach_tinh từ tinh_per_m2: true → 'per_m2'; false → 'flat'.

Revision ID: 0011_addon_cach_tinh
Revises: 0010_product_gia_min
Create Date: 2026-05-07
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_addon_cach_tinh"
down_revision: Union[str, None] = "0010_product_gia_min"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_addons",
        sa.Column(
            "cach_tinh",
            sa.String(length=16),
            server_default="flat",
            nullable=False,
        ),
        schema="shared",
    )
    # Backfill từ flag cũ
    op.execute(
        "UPDATE shared.product_addons "
        "SET cach_tinh = 'per_m2' "
        "WHERE tinh_per_m2 IS TRUE"
    )


def downgrade() -> None:
    op.drop_column("product_addons", "cach_tinh", schema="shared")
