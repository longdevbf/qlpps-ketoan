"""view ketoan.v_nhom_no_don: tiến trình 'Đã có hàng' tính là NỢ THỰC, không còn là dự kiến.

Quyết định giám đốc 01/10/2026 (đảo nhóm đã chốt 28-29/09 ở q6): nhà cung cấp (Chiến Phương, Chị Lan Đệm,
Hoàng Phát…) đều tính các đơn 'Đã có hàng' là nợ thật, và luật định khoản v1.1 ghi hàng về là Nợ 156 / Có 331.
Ví dụ: Chiến Phương đơn NV26001-26-00033 (11.500.000) từng bị trừ khỏi nợ thực nên màn hiện 180.953.000
thay vì 192.453.000. Còn 'dự kiến' = đặt hàng, đang sx.

Production đã được áp bằng SQL (Tài liệu/ban-giao-2026-09-30/deploy-01-10/prod_view_da_co_hang_la_no_thuc.sql);
migration này để dev và các môi trường khác giống production. Chỉ đổi định nghĩa view, không đổi bảng.

Revision ID: q15_2026_10_01
Revises: q14_2026_10_01
"""
from typing import Union

from alembic import op

revision: str = "q15_2026_10_01"
down_revision: Union[str, None] = "q14_2026_10_01"
branch_labels = None
depends_on = None

_VIEW = """
CREATE OR REPLACE VIEW ketoan.v_nhom_no_don AS
SELECT
    p.id AS po_id,
    p.ref_bao_gia AS ma_bao_gia,
    q.tien_trinh_mh,
    CASE
        WHEN lower(coalesce(q.tien_trinh_mh, '') COLLATE "und-x-icu")
             IN ({thuc})
          OR lower(coalesce(p.status, '') COLLATE "und-x-icu") = 'hoàn thành'
            THEN 'thuc'
        WHEN lower(coalesce(q.tien_trinh_mh, '') COLLATE "und-x-icu")
             IN ({du_kien})
            THEN 'du_kien'
        ELSE 'can_kiem'
    END AS nhom_no
FROM muahang.purchase_orders p
LEFT JOIN baogia.quotes q ON q.quote_number = p.ref_bao_gia
"""


def upgrade() -> None:
    op.execute(_VIEW.format(
        thuc="'đã có hàng', 'đã lấy hàng', 'đang giao', 'đã giao', 'hoàn thành'",
        du_kien="'đặt hàng', 'đang sx'",
    ))


def downgrade() -> None:
    op.execute(_VIEW.format(
        thuc="'đã lấy hàng', 'đang giao', 'đã giao', 'hoàn thành'",
        du_kien="'đặt hàng', 'đang sx', 'đã có hàng'",
    ))
