"""M2 BOM Giá Vốn — bom_master + bom_item + FK ketoan.product.bom_id.

Tạo 2 bảng cho module BOM (M2, agent M2 BOM Giá Vốn):
  - bom_master: header (mã BOM, tên, category_id, hiệu lực, tổng giá vốn cache, active)
  - bom_item: chi tiết NVL (tên, dvt, số lượng, đơn giá, thành tiền GENERATED)
  - Add FK constraint ketoan.product.bom_id → ketoan.bom_master(id) ON DELETE SET NULL
    (cột bom_id đã được tạo NULL ở M1; giờ thêm FK).

Quy ước Papasan:
  - 1 BOM gắn theo nhóm SP (category_id) — nhiều SP cùng nhóm dùng chung
  - Phiên bản BOM bằng cặp effective_from/effective_to
  - tong_gia_von được cache trên header — recalc khi item đổi (service bom_calc)

Revision ID: m2bom_2026_04_28
Revises: m5kk_2026_04_28
Create Date: 2026-04-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m2bom_2026_04_28"
down_revision: Union[str, None] = "m5kk_2026_04_28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── bom_master ──────────────────────────────────────────────────────
    op.create_table(
        "bom_master",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ma_bom", sa.String(32), nullable=False),
        sa.Column("ten_bom", sa.String(255), nullable=False),
        sa.Column(
            "category_id", sa.Integer(),
            sa.ForeignKey("ketoan.product_category.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "effective_from", sa.Date(),
            nullable=False, server_default=sa.func.current_date(),
        ),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column(
            "tong_gia_von", sa.Numeric(15, 2),
            nullable=False, server_default="0",
        ),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("ma_bom", name="uq_bom_master_ma_bom"),
        schema="ketoan",
    )
    op.create_index("ix_bom_category", "bom_master", ["category_id"], schema="ketoan")
    op.create_index("ix_bom_active", "bom_master", ["active"], schema="ketoan")

    # ─── bom_item ────────────────────────────────────────────────────────
    op.create_table(
        "bom_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "bom_id", sa.Integer(),
            sa.ForeignKey("ketoan.bom_master.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ten_nvl", sa.String(255), nullable=False),
        sa.Column("dvt", sa.String(32), nullable=True),
        sa.Column("so_luong", sa.Numeric(15, 2), nullable=False),
        sa.Column("don_gia", sa.Numeric(15, 2), nullable=False),
        sa.Column(
            "thanh_tien", sa.Numeric(15, 2),
            sa.Computed("so_luong * don_gia", persisted=True),
            nullable=False,
        ),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        schema="ketoan",
    )
    op.create_index("ix_bom_item_bom", "bom_item", ["bom_id"], schema="ketoan")

    # ─── FK ketoan.product.bom_id → ketoan.bom_master(id) ────────────────
    op.create_foreign_key(
        "fk_product_bom",
        source_table="product", referent_table="bom_master",
        local_cols=["bom_id"], remote_cols=["id"],
        ondelete="SET NULL",
        source_schema="ketoan", referent_schema="ketoan",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_product_bom", "product",
        type_="foreignkey", schema="ketoan",
    )
    op.drop_index("ix_bom_item_bom", table_name="bom_item", schema="ketoan")
    op.drop_table("bom_item", schema="ketoan")
    op.drop_index("ix_bom_active", table_name="bom_master", schema="ketoan")
    op.drop_index("ix_bom_category", table_name="bom_master", schema="ketoan")
    op.drop_table("bom_master", schema="ketoan")
