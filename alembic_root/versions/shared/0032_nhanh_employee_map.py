"""Nhanh employee mapping — Papasan username ↔ Nhanh saleId.

Revision ID: 0032_nhanh_employee_map
Revises: 0031_mai_insights
Create Date: 2026-05-27

Bảng `shared.nhanh_employee_map` chứa mapping NV Papasan ↔ Nhanh saleId.
Workflow: khi đẩy lead/quote sang Nhanh, lookup saleId từ bảng này → gắn
vào payload /v3.0/bill/addretail (lead) hoặc /api/order/add (quote) để
Nhanh.vn xác định "Người tạo" (trigger ZNS workflow).

Seed 7 NV từ Google Sheet (4 Đơn Hàng + 3 Bán lẻ).
"""
from alembic import op


revision = "0032_nhanh_employee_map"
down_revision = "0031_mai_insights"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")

    op.execute("""
        CREATE TABLE IF NOT EXISTS shared.nhanh_employee_map (
            papasan_username VARCHAR(64) PRIMARY KEY,
            full_name        VARCHAR(255),
            nhanh_sale_id    INTEGER NOT NULL,
            loai             VARCHAR(16),
            active           BOOLEAN NOT NULL DEFAULT TRUE,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_nhanh_emp_sale_id
        ON shared.nhanh_employee_map(nhanh_sale_id)
    """)

    # Seed 7 NV (4 don_hang + 3 ban_le)
    op.execute("""
        INSERT INTO shared.nhanh_employee_map
            (papasan_username, full_name, nhanh_sale_id, loai)
        VALUES
            ('nv26013',   'Nguyễn Quang Linh',     3607111, 'don_hang'),
            ('nv26012',   'Cao Việt Thái',         3607108, 'don_hang'),
            ('nv26011',   'Trương Thị Thuỳ Trang', 3607099, 'don_hang'),
            ('nv26010',   'Đoàn Thị Diễm Hương',   3607098, 'don_hang'),
            ('nv26015',   'Triệu Đức Dương',       3602891, 'ban_le'),
            ('nv26001',   'Triệu Vy',              3601861, 'ban_le'),
            ('nv26007_3', 'Đỗ Quang Thắng',        3613823, 'ban_le')
        ON CONFLICT (papasan_username) DO UPDATE SET
            full_name = EXCLUDED.full_name,
            nhanh_sale_id = EXCLUDED.nhanh_sale_id,
            loai = EXCLUDED.loai,
            updated_at = NOW()
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS shared.idx_nhanh_emp_sale_id")
    op.execute("DROP TABLE IF EXISTS shared.nhanh_employee_map")
