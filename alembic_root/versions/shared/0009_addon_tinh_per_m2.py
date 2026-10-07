"""shared.product_addons: thêm cột tinh_per_m2 BOOL.

Cờ per-addon đánh dấu addon được tính theo m² (giá addon × diện tích SP)
thay vì cộng phẳng. Trước đây hardcoded theo tên SP (Tủ đa năng / Tủ áo)
trong baogia FE → giờ user tự khai báo từng addon ở Kế Toán.

NULL/false = cộng thẳng (mặc định); true = giá × m².

Revision ID: 0009_addon_tinh_per_m2
Revises: 0008_product_attr_per_product
Create Date: 2026-05-07
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_addon_tinh_per_m2"
down_revision: Union[str, None] = "0008_product_attr_per_product"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_addons",
        sa.Column(
            "tinh_per_m2",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        schema="shared",
    )


def downgrade() -> None:
    op.drop_column("product_addons", "tinh_per_m2", schema="shared")
