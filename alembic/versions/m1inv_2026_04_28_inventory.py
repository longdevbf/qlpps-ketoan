"""M1 Inventory — product_category + product + inventory_balance + inventory_movement + kiem_ke.

Tạo 5 bảng cho module Sản Phẩm + Tồn Kho (M1, agent M1).

Revision ID: m1inv_2026_04_28
Revises: 0007_chi_phi_bridges
Create Date: 2026-04-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "m1inv_2026_04_28"
down_revision: Union[str, None] = "0007_chi_phi_bridges"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── product_category ─────────────────────────────────────────────────
    op.create_table(
        "product_category",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ma_nhom", sa.String(32), nullable=False),
        sa.Column("ten_nhom", sa.String(128), nullable=False),
        sa.Column(
            "parent_id", sa.Integer(),
            sa.ForeignKey("ketoan.product_category.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("ma_nhom", name="uq_product_category_ma_nhom"),
        schema="ketoan",
    )
    op.create_index("ix_pc_parent", "product_category", ["parent_id"], schema="ketoan")
    op.create_index("ix_pc_active", "product_category", ["active"], schema="ketoan")

    # ─── product ──────────────────────────────────────────────────────────
    op.create_table(
        "product",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ma_sp", sa.String(64), nullable=False),
        sa.Column("ten_sp", sa.String(255), nullable=False),
        sa.Column(
            "category_id", sa.Integer(),
            sa.ForeignKey("ketoan.product_category.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("dvt", sa.String(32), nullable=False, server_default="cái"),
        sa.Column(
            "attributes", postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "gia_ban_mac_dinh", sa.Numeric(15, 2),
            nullable=False, server_default="0",
        ),
        sa.Column("bom_id", sa.Integer(), nullable=True),
        sa.Column("hinh_anh", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("ma_sp", name="uq_inv_product_ma_sp"),
        schema="ketoan",
    )
    op.create_index("ix_inv_product_category", "product", ["category_id"], schema="ketoan")
    op.create_index("ix_inv_product_active", "product", ["active"], schema="ketoan")
    op.create_index("ix_inv_product_ten_sp", "product", ["ten_sp"], schema="ketoan")

    # ─── inventory_balance ───────────────────────────────────────────────
    op.create_table(
        "inventory_balance",
        sa.Column(
            "product_id", sa.Integer(),
            sa.ForeignKey("ketoan.product.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("so_luong_ton", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("gia_von_bq", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("gia_tri_ton", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("ton_min", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("ton_max", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column(
            "last_updated", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        schema="ketoan",
    )

    # ─── inventory_movement ──────────────────────────────────────────────
    op.create_table(
        "inventory_movement",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ngay", sa.Date(), nullable=False),
        sa.Column(
            "product_id", sa.Integer(),
            sa.ForeignKey("ketoan.product.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("loai", sa.String(20), nullable=False),
        sa.Column("so_luong", sa.Numeric(15, 2), nullable=False),
        sa.Column("don_gia", sa.Numeric(15, 2), nullable=False),
        sa.Column("thanh_tien", sa.Numeric(15, 2), nullable=False),
        sa.Column("source_app", sa.String(32), nullable=True),
        sa.Column("source_doc_id", sa.String(64), nullable=True),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        schema="ketoan",
    )
    op.create_index(
        "ix_im_product_ngay", "inventory_movement",
        ["product_id", "ngay"], schema="ketoan",
    )
    op.create_index("ix_im_loai", "inventory_movement", ["loai"], schema="ketoan")
    op.create_index(
        "ix_im_source", "inventory_movement",
        ["source_app", "source_doc_id"], schema="ketoan",
    )
    op.create_index("ix_im_ngay", "inventory_movement", ["ngay"], schema="ketoan")
    # Idempotent: 1 movement / source_doc_id (chỉ áp khi source_doc_id NOT NULL)
    op.execute(
        "CREATE UNIQUE INDEX uq_im_source_doc "
        "ON ketoan.inventory_movement(source_app, source_doc_id) "
        "WHERE source_app IS NOT NULL AND source_doc_id IS NOT NULL"
    )

    # ─── kiem_ke ─────────────────────────────────────────────────────────
    op.create_table(
        "kiem_ke",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ngay", sa.Date(), nullable=False),
        sa.Column(
            "product_id", sa.Integer(),
            sa.ForeignKey("ketoan.product.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("ton_so_sach", sa.Numeric(15, 2), nullable=True),
        sa.Column("ton_thuc_te", sa.Numeric(15, 2), nullable=True),
        sa.Column("chenh_lech", sa.Numeric(15, 2), nullable=True),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        schema="ketoan",
    )
    op.create_index("ix_kk_ngay", "kiem_ke", ["ngay"], schema="ketoan")
    op.create_index("ix_kk_product", "kiem_ke", ["product_id"], schema="ketoan")


def downgrade() -> None:
    op.drop_index("ix_kk_product", table_name="kiem_ke", schema="ketoan")
    op.drop_index("ix_kk_ngay", table_name="kiem_ke", schema="ketoan")
    op.drop_table("kiem_ke", schema="ketoan")

    op.execute("DROP INDEX IF EXISTS ketoan.uq_im_source_doc")
    op.drop_index("ix_im_ngay", table_name="inventory_movement", schema="ketoan")
    op.drop_index("ix_im_source", table_name="inventory_movement", schema="ketoan")
    op.drop_index("ix_im_loai", table_name="inventory_movement", schema="ketoan")
    op.drop_index("ix_im_product_ngay", table_name="inventory_movement", schema="ketoan")
    op.drop_table("inventory_movement", schema="ketoan")

    op.drop_table("inventory_balance", schema="ketoan")

    op.drop_index("ix_inv_product_ten_sp", table_name="product", schema="ketoan")
    op.drop_index("ix_inv_product_active", table_name="product", schema="ketoan")
    op.drop_index("ix_inv_product_category", table_name="product", schema="ketoan")
    op.drop_table("product", schema="ketoan")

    op.drop_index("ix_pc_active", table_name="product_category", schema="ketoan")
    op.drop_index("ix_pc_parent", table_name="product_category", schema="ketoan")
    op.drop_table("product_category", schema="ketoan")
