"""Add view ketoan.v_nhom_no_don — phân loại nợ NCC thực/dự kiến/cần kiểm theo từng đơn mua.

Công nợ NCC hiện ghi ở HAI bảng độc lập, không đồng bộ: `muahang.congno` và
`ketoan.cong_no` (ref_source='muahang'/'muahang_po') — cùng một câu hỏi "còn nợ
NCC" ra nhiều số khác nhau vì mỗi nơi (Mua hàng, Kế toán, CEO, ~20 chỗ ở 4 app)
tự định nghĩa "đơn đã xong" (dự kiến hay thực) theo cách riêng.

Quyết định người dùng 28-29/09/2026: `ketoan.cong_no` VẪN là sổ chuẩn — migration
này KHÔNG gộp 2 sổ, KHÔNG đụng cột "đã trả" nào. View chỉ trả lời đúng MỘT câu:
"đơn mua này (theo PO) đang ở nhóm nợ nào" — nơi đọc tự LEFT JOIN vào theo
`ref_id`/`ma_don` rồi COALESCE(nhom_no, 'can_kiem').

Ba nhóm (chốt bởi người dùng, dựa nhãn baogia.quotes.tien_trinh_mh hoặc
muahang.purchase_orders.status):
  - thuc:     đã lấy hàng, đang giao, đã giao, hoàn thành (hoặc PO.status='Hoàn Thành')
  - du_kien:  đặt hàng, đang sx, đã có hàng
  - can_kiem: nhãn lạ/NULL, hoặc dòng công nợ không còn PO nào khớp (mồ côi)

BẪY BẮT BUỘC: production có `datctype=C` — `LOWER()` mặc định KHÔNG hạ đúng
chữ hoa có dấu tiếng Việt (`lower('Đã Giao')` vẫn ra 'Đã giao', chữ Đ giữ
nguyên) — đây chính là lỗi collation đã gặp 25/09/2026 ở cong_no_ncc.py:54-60.
Trên dev thì LOWER mặc định lại chạy đúng nên dev không lộ lỗi này — PHẢI ép
`COLLATE "und-x-icu"` (đã xác nhận tồn tại trên cả dev lẫn production) mới ra
kết quả đúng trên cả hai môi trường.

Nối theo `muahang.purchase_orders` (khoá `po_id` ổn định), KHÔNG nối theo
`ma_don` của dòng bên `ketoan.cong_no` — đã kiểm có 3 dòng đổi nhóm tuỳ cách
nối vì `ma_don` là chuỗi tự do, không đáng tin bằng PO.

Revision ID: q6_2026_09_30
Revises: q5_2026_05_19
"""
from typing import Union

from alembic import op

revision: str = "q6_2026_09_30"
down_revision: Union[str, None] = "q5_2026_05_19"
branch_labels = None
depends_on = None


_CREATE_VIEW = """
CREATE OR REPLACE VIEW ketoan.v_nhom_no_don AS
SELECT
    p.id AS po_id,
    p.ref_bao_gia AS ma_bao_gia,
    q.tien_trinh_mh,
    CASE
        WHEN lower(coalesce(q.tien_trinh_mh, '') COLLATE "und-x-icu")
             IN ('đã lấy hàng', 'đang giao', 'đã giao', 'hoàn thành')
          OR lower(coalesce(p.status, '') COLLATE "und-x-icu") = 'hoàn thành'
            THEN 'thuc'
        WHEN lower(coalesce(q.tien_trinh_mh, '') COLLATE "und-x-icu")
             IN ('đặt hàng', 'đang sx', 'đã có hàng')
            THEN 'du_kien'
        ELSE 'can_kiem'
    END AS nhom_no
FROM muahang.purchase_orders p
LEFT JOIN baogia.quotes q ON q.quote_number = p.ref_bao_gia
"""

_DROP_VIEW = "DROP VIEW IF EXISTS ketoan.v_nhom_no_don"


def upgrade() -> None:
    op.execute(_CREATE_VIEW)


def downgrade() -> None:
    # DROP VIEW — view không lưu dữ liệu riêng, chỉ đọc từ muahang/baogia, nên
    # xoá không mất gì; nơi đọc phải tự lùi cách tính trước khi downgrade migration này.
    op.execute(_DROP_VIEW)
