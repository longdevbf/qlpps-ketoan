"""shared products master catalog (move from baogia.products)

Revision ID: 0003_products_master
Revises: 0002_ceo_foundation
Create Date: 2026-04-27

Tách `products` + `product_addons` từ schema `baogia` sang `shared` để tất cả
app dùng chung (ketoan = CRUD, baogia/marketing/saleadmin/muahang = read-only).

Thêm field mới so với baogia.products gốc:
    - gia_von       : giá vốn (mua hàng + kế toán)
    - hinh_anh      : URL/path ảnh đại diện (marketing chạy ads)
    - mo_ta         : mô tả dài
    - nhom_hang     : phân loại (Giường / Sofa / Bàn / ...)

Migration tự copy data từ baogia nếu tồn tại, sau đó drop. Idempotent.
Trên fresh DB không có baogia.products, block IF EXISTS bỏ qua an toàn.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_products_master"
down_revision: Union[str, None] = "0002_ceo_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ma_sp", sa.String(64), nullable=False),
        sa.Column("ten_sp", sa.String(255), nullable=False),
        sa.Column("label", sa.String(255)),
        sa.Column("dvt", sa.String(32)),
        sa.Column("unit", sa.String(32)),
        sa.Column("nhom_hang", sa.String(64)),
        sa.Column("gia_co_ban", sa.Numeric(15, 2), server_default="0", nullable=False),
        sa.Column("gia_von", sa.Numeric(15, 2)),
        sa.Column("dimensions", sa.JSON()),
        sa.Column("dim_labels", sa.JSON()),
        sa.Column("sizes", sa.JSON()),
        sa.Column("kich_thuoc_chuan", sa.String(255)),
        sa.Column("mau_chuan", sa.String(128)),
        sa.Column("hinh_anh", sa.String(512)),
        sa.Column("mo_ta", sa.Text()),
        sa.Column("ghi_chu", sa.Text()),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("thu_tu", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("ma_sp", name="uq_products_ma_sp"),
        schema="shared",
    )
    op.create_index("ix_products_ten_sp", "products", ["ten_sp"], schema="shared")
    op.create_index("ix_products_active", "products", ["active"], schema="shared")
    op.create_index("ix_products_nhom_hang", "products", ["nhom_hang"], schema="shared")

    op.create_table(
        "product_addons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("shared.products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ten_addon", sa.String(255), nullable=False),
        sa.Column("gia_addon", sa.Numeric(15, 2), server_default="0", nullable=False),
        sa.Column("dvt", sa.String(32)),
        sa.Column("ghi_chu", sa.Text()),
        sa.Column("thu_tu", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("product_id", "ten_addon", name="uq_product_addon"),
        schema="shared",
    )
    op.create_index(
        "ix_product_addons_product", "product_addons", ["product_id"], schema="shared"
    )

    # Copy data từ baogia.products nếu tồn tại, rồi drop bảng cũ
    op.execute("""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'baogia' AND table_name = 'products'
        ) THEN
            INSERT INTO shared.products (
                id, ma_sp, ten_sp, label, dvt, unit,
                gia_co_ban, dimensions, dim_labels, sizes,
                kich_thuoc_chuan, mau_chuan, ghi_chu, active, thu_tu,
                created_at, updated_at
            )
            SELECT
                id, ma_sp, ten_sp, label, dvt, unit,
                gia_co_ban, dimensions, dim_labels, sizes,
                kich_thuoc_chuan, mau_chuan, ghi_chu, active, thu_tu,
                created_at, updated_at
            FROM baogia.products;

            INSERT INTO shared.product_addons (
                id, product_id, ten_addon, gia_addon, dvt, ghi_chu, thu_tu,
                created_at, updated_at
            )
            SELECT
                id, product_id, ten_addon, gia_addon, dvt, ghi_chu, thu_tu,
                created_at, updated_at
            FROM baogia.product_addons;

            PERFORM setval(
                pg_get_serial_sequence('shared.products', 'id'),
                COALESCE((SELECT MAX(id) FROM shared.products), 1)
            );
            PERFORM setval(
                pg_get_serial_sequence('shared.product_addons', 'id'),
                COALESCE((SELECT MAX(id) FROM shared.product_addons), 1)
            );

            DROP TABLE baogia.product_addons CASCADE;
            DROP TABLE baogia.products CASCADE;
        END IF;
    END $$;
    """)


def downgrade() -> None:
    # Khôi phục baogia.products + baogia.product_addons từ shared (nếu có)
    op.execute("""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'shared' AND table_name = 'products'
        ) THEN
            CREATE TABLE IF NOT EXISTS baogia.products (LIKE shared.products INCLUDING ALL);
            CREATE TABLE IF NOT EXISTS baogia.product_addons (LIKE shared.product_addons INCLUDING ALL);
            INSERT INTO baogia.products SELECT * FROM shared.products;
            INSERT INTO baogia.product_addons SELECT * FROM shared.product_addons;
        END IF;
    END $$;
    """)
    op.drop_index("ix_product_addons_product", table_name="product_addons", schema="shared")
    op.drop_table("product_addons", schema="shared")
    op.drop_index("ix_products_nhom_hang", table_name="products", schema="shared")
    op.drop_index("ix_products_active", table_name="products", schema="shared")
    op.drop_index("ix_products_ten_sp", table_name="products", schema="shared")
    op.drop_table("products", schema="shared")
