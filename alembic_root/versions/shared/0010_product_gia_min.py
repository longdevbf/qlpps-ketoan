"""shared.products: thêm cột gia_min (giá sàn) Numeric(15,2) nullable.

Khi báo giá tính ra giá < gia_min → dùng gia_min làm sàn.
VD: SP met_dai 10tr/m, khách nhập 0.5m → tính bình thường 5tr nhưng
gia_min=10tr → cuối cùng dùng 10tr (giá tối thiểu).

NULL/0 = không áp dụng sàn (mặc định).

Revision ID: 0010_product_gia_min
Revises: 0009_addon_tinh_per_m2
Create Date: 2026-05-07
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_product_gia_min"
down_revision: Union[str, None] = "0009_addon_tinh_per_m2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("gia_min", sa.Numeric(15, 2), nullable=True),
        schema="shared",
    )


def downgrade() -> None:
    op.drop_column("products", "gia_min", schema="shared")
