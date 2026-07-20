"""Phase 6A — Ads phân bổ theo nhóm master + bảng ads_phan_bo_don.

Thay đổi:
1. ALTER `shared.products` thêm cột `nhom_master` ∈ {Đồ Gỗ | Đồ Mây | Dự Án}
   + CHECK constraint + index. Backfill loose match qua ten_sp/nhom_hang.

2. CREATE `ketoan.ads_phan_bo_don` — bảng phân bổ ads theo từng đơn hoàn thành
   theo % giá trị nhóm trong đơn (matching principle). Pool ads "Khác"
   (san_pham không match 3 nhóm) chia đều 3 nhóm.

Revision ID: p6a_2026_04_29
Revises: p6_2026_04_29_so_quy_cf
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p6a_2026_04_29"
down_revision: Union[str, None] = "p6_2026_04_29_so_quy_cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ────────────────────────────────────────────────────────────────────
    # PHẦN 1: ALTER shared.products → thêm nhom_master
    # ────────────────────────────────────────────────────────────────────
    op.execute("""
        ALTER TABLE shared.products
          ADD COLUMN IF NOT EXISTS nhom_master VARCHAR(32);
    """)

    # CHECK constraint — Postgres không support IF NOT EXISTS cho ADD CONSTRAINT
    # → dùng DO block kiểm tra trước
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_products_nhom_master'
                  AND conrelid = 'shared.products'::regclass
            ) THEN
                ALTER TABLE shared.products
                  ADD CONSTRAINT ck_products_nhom_master
                  CHECK (nhom_master IS NULL
                         OR nhom_master IN ('Đồ Gỗ', 'Đồ Mây', 'Dự Án'));
            END IF;
        END$$;
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_products_nhom_master
          ON shared.products(nhom_master);
    """)

    # Backfill loose match — ưu tiên Dự Án trước (rare), Đồ Gỗ, Đồ Mây
    op.execute("""
        UPDATE shared.products SET nhom_master = 'Dự Án'
          WHERE nhom_master IS NULL
            AND (LOWER(ten_sp) LIKE '%dự án%' OR LOWER(ten_sp) LIKE '%du an%'
                 OR LOWER(COALESCE(nhom_hang, '')) LIKE '%dự án%'
                 OR LOWER(COALESCE(nhom_hang, '')) LIKE '%du an%');
    """)
    op.execute("""
        UPDATE shared.products SET nhom_master = 'Đồ Gỗ'
          WHERE nhom_master IS NULL
            AND (LOWER(ten_sp) LIKE '%gỗ%' OR LOWER(ten_sp) LIKE '%go%'
                 OR LOWER(COALESCE(nhom_hang, '')) LIKE '%gỗ%'
                 OR LOWER(COALESCE(nhom_hang, '')) LIKE '%go%');
    """)
    op.execute("""
        UPDATE shared.products SET nhom_master = 'Đồ Mây'
          WHERE nhom_master IS NULL
            AND (LOWER(ten_sp) LIKE '%mây%' OR LOWER(ten_sp) LIKE '%may%'
                 OR LOWER(COALESCE(nhom_hang, '')) LIKE '%mây%'
                 OR LOWER(COALESCE(nhom_hang, '')) LIKE '%may%');
    """)

    # ────────────────────────────────────────────────────────────────────
    # PHẦN 2: CREATE ketoan.ads_phan_bo_don
    # ────────────────────────────────────────────────────────────────────
    op.create_table(
        "ads_phan_bo_don",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("thang_chi_ads", sa.String(length=7), nullable=False),
        sa.Column("nhom_master", sa.String(length=32), nullable=False),
        sa.Column("quote_number", sa.String(length=64), nullable=True),
        sa.Column("ngay_chot", sa.Date, nullable=True),
        sa.Column("value_nhom_trong_don", sa.Numeric(15, 2), nullable=True),
        sa.Column("ty_le_pool", sa.Numeric(7, 4), nullable=True),
        sa.Column("so_tien_phan_bo", sa.Numeric(15, 2), nullable=False),
        sa.Column("loai_phan_bo", sa.String(length=20), nullable=False),
        sa.Column("vc_status", sa.String(length=20), nullable=True),
        sa.Column("thang_hoan_thanh", sa.String(length=7), nullable=True),
        sa.Column("cpa_nhom_snapshot", sa.Numeric(15, 2), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            "nhom_master IN ('Đồ Gỗ', 'Đồ Mây', 'Dự Án')",
            name="ck_apb_nhom",
        ),
        sa.CheckConstraint(
            "loai_phan_bo IN ('theo_nhom', 'redistribute_khac', 'no_match')",
            name="ck_apb_loai",
        ),
        schema="ketoan",
    )

    # UNIQUE partial index — 1 quote × 1 nhóm × 1 tháng chi chỉ 1 dòng
    # (no_match dòng nhiều quote_number=NULL → loại khỏi unique)
    op.execute("""
        CREATE UNIQUE INDEX uq_apb_thang_nhom_quote
          ON ketoan.ads_phan_bo_don(thang_chi_ads, nhom_master, quote_number)
          WHERE quote_number IS NOT NULL;
    """)

    op.create_index(
        "ix_apb_thang_chi", "ads_phan_bo_don",
        ["thang_chi_ads"], schema="ketoan",
    )
    op.create_index(
        "ix_apb_thang_ht", "ads_phan_bo_don",
        ["thang_hoan_thanh"], schema="ketoan",
    )
    op.create_index(
        "ix_apb_quote", "ads_phan_bo_don",
        ["quote_number"], schema="ketoan",
    )


def downgrade() -> None:
    # Drop ads_phan_bo_don
    op.drop_index("ix_apb_quote", table_name="ads_phan_bo_don", schema="ketoan")
    op.drop_index("ix_apb_thang_ht", table_name="ads_phan_bo_don", schema="ketoan")
    op.drop_index("ix_apb_thang_chi", table_name="ads_phan_bo_don", schema="ketoan")
    op.execute("DROP INDEX IF EXISTS ketoan.uq_apb_thang_nhom_quote;")
    op.drop_table("ads_phan_bo_don", schema="ketoan")

    # Revert shared.products.nhom_master
    op.execute("DROP INDEX IF EXISTS shared.ix_products_nhom_master;")
    op.execute("""
        ALTER TABLE shared.products
          DROP CONSTRAINT IF EXISTS ck_products_nhom_master;
    """)
    op.execute("""
        ALTER TABLE shared.products
          DROP COLUMN IF EXISTS nhom_master;
    """)
