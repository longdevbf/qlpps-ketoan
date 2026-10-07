"""shared.product_attributes — danh mục thuộc tính theo nhóm master SP.

Bảng flat (1 row = 1 (nhom_master, attr_key, attr_value)) cho Kế Toán
quản lý CRUD ở /thuoc-tinh; các app khác READ để render dropdown khi
thêm/sửa SP (Đồ Gỗ → Màu gỗ → [Walnut/Oak/...]).

Revision ID: 0004_product_attributes
Revises: 0003_products_master
Create Date: 2026-05-05
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_product_attributes"
down_revision: Union[str, None] = "0003_products_master"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_attributes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nhom_master", sa.String(length=64), nullable=False),
        sa.Column("attr_key", sa.String(length=64), nullable=False),
        sa.Column("attr_value", sa.String(length=255), nullable=False),
        sa.Column("thu_tu", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "active", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "nhom_master", "attr_key", "attr_value",
            name="uq_product_attributes_triple",
        ),
        schema="shared",
    )
    op.create_index(
        "ix_product_attributes_nhom_key",
        "product_attributes",
        ["nhom_master", "attr_key"],
        schema="shared",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_product_attributes_nhom_key",
        table_name="product_attributes",
        schema="shared",
    )
    op.drop_table("product_attributes", schema="shared")
