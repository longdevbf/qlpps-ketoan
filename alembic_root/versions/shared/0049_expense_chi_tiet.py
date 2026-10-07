"""Đề nghị thanh toán — các cột chi tiết thật thay vì nhồi vào `muc_dich`.

Revision ID: 0049_expense_chi_tiet
Revises: 0048_de_xuat_cham_cong
Create Date: 2026-10-05

Form Đề nghị thanh toán (2026-09-25) hỏi người thụ hưởng / số tài khoản / ngân hàng /
hình thức, nhưng model không có cột nào cho chúng nên JS **nối hết vào `muc_dich`**
dưới dạng văn bản. Hệ quả: không lọc được, không đối chiếu được, và khi bấm Chi thì
sổ chi phí không biết tiền trả cho ai.

Thêm cột thật cho đúng những gì form đã hỏi, cộng `ma_don` (đơn hàng liên quan) và
`loai_chi_phi` (tên loại trong `ketoan.loai_chi_phi` — danh mục 32 loại mà màn Thu chi
vẫn dùng). `loai_chi` cũ GIỮ NGUYÊN: 182 bản ghi đang dùng 6 mã cũ, và 7 app còn lại
vẫn gửi 6 mã đó.

Tất cả đều nullable — đề xuất cũ và các app chưa cập nhật form vẫn tạo được như trước.
"""
from alembic import op
import sqlalchemy as sa


revision = "0049_expense_chi_tiet"
down_revision = "0048_de_xuat_cham_cong"
branch_labels = None
depends_on = None


_COT = (
    ("loai_chi_phi", sa.String(128)),     # tên loại trong ketoan.loai_chi_phi
    ("nguoi_thu_huong", sa.String(255)),  # người/đơn vị NHẬN tiền
    ("so_tk_nhan", sa.String(64)),
    ("ngan_hang_nhan", sa.String(128)),
    ("hinh_thuc", sa.String(16)),         # ck | tm
    ("ma_don", sa.String(64)),            # đơn hàng liên quan (baogia.quotes.quote_number)
)


def upgrade() -> None:
    for ten, kieu in _COT:
        op.add_column("expense_requests", sa.Column(ten, kieu, nullable=True),
                      schema="shared")
    op.create_index("ix_expense_requests_ma_don", "expense_requests", ["ma_don"],
                    schema="shared")
    op.create_index("ix_expense_requests_loai_chi_phi", "expense_requests",
                    ["loai_chi_phi"], schema="shared")


def downgrade() -> None:
    op.drop_index("ix_expense_requests_loai_chi_phi", "expense_requests", schema="shared")
    op.drop_index("ix_expense_requests_ma_don", "expense_requests", schema="shared")
    for ten, _ in reversed(_COT):
        op.drop_column("expense_requests", ten, schema="shared")
