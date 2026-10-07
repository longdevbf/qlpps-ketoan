"""Ngày lễ — thêm cột `dip` (gom nhóm theo dịp lễ, điều chỉnh ngày nghỉ thực/năm).

Mỗi dịp lễ (Tết Nguyên Đán, Quốc Khánh, 30/4 & 1/5, ...) gom nhiều bản ghi ngày
nghỉ THỰC; số ngày mỗi năm khác nhau (nghỉ bù/hoán đổi) → HR tự điều chỉnh.

Revision ID: 0047_ngay_le_dip
Revises: 0046_ngay_le
Create Date: 2026-08-27
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0047_ngay_le_dip"
down_revision: Union[str, None] = "0046_ngay_le"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IDEMPOTENT (anh Quang 2026-08-31): cột dip có thể đã được thêm bằng ALTER tay
    # trên prod trước khi chạy migration → dùng IF NOT EXISTS để upgrade không lỗi.
    op.execute(
        "ALTER TABLE hcns.ngay_le ADD COLUMN IF NOT EXISTS dip VARCHAR(255)"
    )
    # Backfill dịp cho các bản ghi cũ theo tên (best-effort).
    op.execute("""
        UPDATE hcns.ngay_le SET dip = CASE
            WHEN ten ILIKE '%nguyên đán%' OR ten ILIKE '%tết%' AND ten NOT ILIKE '%dương%' THEN 'Tết Nguyên Đán'
            WHEN ten ILIKE '%dương%'                         THEN 'Tết Dương lịch'
            WHEN ten ILIKE '%giỗ tổ%' OR ten ILIKE '%hùng vương%' THEN 'Giỗ Tổ Hùng Vương'
            WHEN ten ILIKE '%giải phóng%' OR ten ILIKE '%30/4%' OR ten ILIKE '%lao động%' OR ten ILIKE '%1/5%' THEN '30/4 & 1/5'
            WHEN ten ILIKE '%khánh%' OR ten ILIKE '%2/9%'    THEN 'Quốc Khánh'
            ELSE ten
        END
        WHERE dip IS NULL
    """)


def downgrade() -> None:
    op.drop_column("ngay_le", "dip", schema="hcns")
