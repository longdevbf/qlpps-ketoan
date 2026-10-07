"""shared.product_attributes: thêm cột coeff (Numeric 6,3 nullable).

Cột coeff dùng cho phan_khuc / phong_cach để lưu hệ số nhân giá
(VD: Bản Plus = 1.25, Indochine = 1.4). NULL với các attr_key khác
(vat_lieu, mau_go, mau_vai, mau_da, loai_son…).

Revision ID: 0006_product_attr_coeff
Revises: 0005_products_attributes_field
Create Date: 2026-05-06
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_product_attr_coeff"
down_revision: Union[str, None] = "0005_products_attributes_field"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_attributes",
        sa.Column("coeff", sa.Numeric(6, 3), nullable=True),
        schema="shared",
    )


def downgrade() -> None:
    op.drop_column("product_attributes", "coeff", schema="shared")
