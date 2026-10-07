"""shared.products: thêm cột attributes JSONB.

Lưu các giá trị thuộc tính được chọn từ danh mục `shared.product_attributes`
(VD: {"Màu gỗ": "Walnut", "Vân gỗ": "Vân thẳng"}). FE dùng dropdown khi
nhom_master được chọn → gán vào attributes JSONB. Các app khác READ.

Revision ID: 0005_products_attributes_field
Revises: 0004_product_attributes
Create Date: 2026-05-05
"""
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0005_products_attributes_field"
down_revision: Union[str, None] = "0004_product_attributes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "attributes",
            JSONB(),
            server_default="{}",
            nullable=False,
        ),
        schema="shared",
    )


def downgrade() -> None:
    op.drop_column("products", "attributes", schema="shared")
