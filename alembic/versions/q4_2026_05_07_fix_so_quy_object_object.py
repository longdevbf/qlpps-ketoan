"""Fix so_quy.tai_khoan = '[object Object]' do bug FE form khoản vay.

Bug FE: dropdown TK giải ngân/trả nợ render `kv_esc(o)` trong khi `o` là object
{id, ten_tk, ...} → option value = "[object Object]" → SoQuy lưu sai → dashboard
JOIN với `tai_khoan_nh.ten_tk` không match → âm quỹ tiền mặt.

Migration:
- Với mỗi so_quy có tai_khoan='[object Object]' AND lien_quan ILIKE 'vay_%':
  → JOIN ngược ra khoan_vay để lấy tai_khoan_giai_ngan đúng. Nếu khoan_vay
    cũng đã hỏng (= '[object Object]') thì set NULL để admin chỉnh tay.
- Set tai_khoan_giai_ngan='[object Object]' của khoan_vay → NULL (data hỏng).

Revision ID: q4_2026_05_07
Revises: q3_2026_05_04
"""
from typing import Union

from alembic import op


revision: str = "q4_2026_05_07"
down_revision: Union[str, None] = "q3_2026_05_04"
branch_labels = None
depends_on = None


_BAD = "[object Object]"


def upgrade() -> None:
    # 1. Set so_quy.tai_khoan = NULL khi value = '[object Object]'
    #    (FE bug: dropdown gửi object stringified)
    op.execute(f"""
        UPDATE ketoan.so_quy
        SET tai_khoan = NULL
        WHERE tai_khoan = '{_BAD}'
    """)

    # 2. Tương tự với khoan_vay.tai_khoan_giai_ngan
    op.execute(f"""
        UPDATE ketoan.khoan_vay
        SET tai_khoan_giai_ngan = NULL
        WHERE tai_khoan_giai_ngan = '{_BAD}'
    """)


def downgrade() -> None:
    # Không thể downgrade — data đã được sửa, không khôi phục giá trị sai.
    pass
