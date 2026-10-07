"""shared.product_attributes: thêm product_id (nullable) cho per-product overrides.

Trước: thuộc tính chung cho cả nhom_master (Đồ Gỗ → Bản Plus 1.25 áp dụng
mọi SP trong nhóm). Giờ: mỗi SP có thể khai báo riêng (Sofa có Mây/Cói,
Bàn ăn không có) → product_id NOT NULL = override; NULL = mặc định nhóm.

Unique constraint cũ (nhom_master, attr_key, attr_value) thay bằng 2
partial unique indexes:
- product_id IS NULL → unique per (nhom_master, attr_key, attr_value)
- product_id IS NOT NULL → unique per (product_id, attr_key, attr_value)

FE merge: ưu tiên per-product, fallback nhom-default.

Revision ID: 0008_product_attr_per_product
Revises: 0007_seed_product_attributes
Create Date: 2026-05-06
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_product_attr_per_product"
down_revision: Union[str, None] = "0007_seed_product_attributes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_attributes",
        sa.Column("product_id", sa.Integer(), nullable=True),
        schema="shared",
    )
    # Bỏ unique cũ (full triple) — sẽ thay bằng 2 partial unique
    op.drop_constraint(
        "uq_product_attributes_triple",
        "product_attributes",
        schema="shared",
        type_="unique",
    )
    # Partial unique: nhom-default (product_id IS NULL)
    op.create_index(
        "uq_product_attributes_default",
        "product_attributes",
        ["nhom_master", "attr_key", "attr_value"],
        unique=True,
        postgresql_where=sa.text("product_id IS NULL"),
        schema="shared",
    )
    # Partial unique: per-product (product_id IS NOT NULL)
    op.create_index(
        "uq_product_attributes_per_product",
        "product_attributes",
        ["product_id", "attr_key", "attr_value"],
        unique=True,
        postgresql_where=sa.text("product_id IS NOT NULL"),
        schema="shared",
    )
    op.create_index(
        "ix_product_attributes_product_id",
        "product_attributes",
        ["product_id"],
        schema="shared",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_product_attributes_product_id",
        table_name="product_attributes",
        schema="shared",
    )
    op.drop_index(
        "uq_product_attributes_per_product",
        table_name="product_attributes",
        schema="shared",
    )
    op.drop_index(
        "uq_product_attributes_default",
        table_name="product_attributes",
        schema="shared",
    )
    op.create_unique_constraint(
        "uq_product_attributes_triple",
        "product_attributes",
        ["nhom_master", "attr_key", "attr_value"],
        schema="shared",
    )
    op.drop_column("product_attributes", "product_id", schema="shared")
