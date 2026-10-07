"""Add nhanh_username column + populate 7 NV.

Revision ID: 0033_nhanh_username
Revises: 0032_nhanh_employee_map
Create Date: 2026-05-27

Nhanh.vn API /api/customer/add yêu cầu field `saleName` = Nhanh username
(không phải saleId number) để populate cột "Người tạo" KH + trigger ZNS.

Lookup từ Nhanh /v3.0/business/user?ids=[7 saleId] đã verify.
"""
from alembic import op


revision = "0033_nhanh_username"
# Merge 2 head migrations (0032_directive_status_v2 đã có sẵn trên VPS từ
# nhánh khác). 0033 này là merge point.
down_revision = ("0032_nhanh_employee_map", "0032_directive_status_v2")
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE shared.nhanh_employee_map ADD COLUMN IF NOT EXISTS nhanh_username VARCHAR(64)")
    op.execute("""
        UPDATE shared.nhanh_employee_map SET nhanh_username=CASE papasan_username
            WHEN 'nv26013'   THEN 'quanglinhpps'
            WHEN 'nv26012'   THEN 'thaitram'
            WHEN 'nv26011'   THEN 'kd4pps612'
            WHEN 'nv26010'   THEN 'kdpps233'
            WHEN 'nv26015'   THEN 'duongtvtt'
            WHEN 'nv26001'   THEN 'leadmkt123'
            WHEN 'nv26007_3' THEN 'thangads123'
            ELSE nhanh_username
        END
        WHERE papasan_username IN
            ('nv26013','nv26012','nv26011','nv26010','nv26015','nv26001','nv26007_3')
    """)


def downgrade():
    op.execute("ALTER TABLE shared.nhanh_employee_map DROP COLUMN IF EXISTS nhanh_username")
