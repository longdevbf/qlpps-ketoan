"""Đề xuất chi — người THỰC NHẬN tiền + ngày nhận, kế toán ghi lúc bấm Chi (Việc 3).

Revision ID: 0050_expense_nguoi_nhan
Revises: 0049_expense_chi_tiet
Create Date: 2026-10-08

Hộp "Chi tiền và ghi sổ" (màn Duyệt chi Kế toán) nay cho kế toán ghi người nhận + ngày nhận trước khi ghi
sổ. Lưu trên CHỨNG TỪ GỐC `shared.expense_requests` để 8 app cùng thấy, và ở `ketoan.so_quy` (doi_tuong_ten
có sẵn + ngay_nhan của migration ketoan q17). Cột RIÊNG, không ghi đè `nguoi_thu_huong` (0049): đó là bản người
đề nghị khai — ghi đè là mất bản gốc để đối chiếu.

Hai cột nullable, không default, KHÔNG backfill — đề xuất cũ giữ NULL; 7 app chưa cập nhật form vẫn chi được
như trước (bỏ trống = không ghi).

THỨ TỰ BẮT BUỘC khi lên production: chạy migration này (và q17 của schema ketoan) TRƯỚC khi BẤT KỲ container
nào chạy bản shared/ mới — schema shared dùng chung một Postgres, chạy một lần là đủ cho cả 8 app. ORM liệt kê
MỌI cột của model trong SELECT → shared mới gặp DB chưa có cột thì mọi endpoint /api/duyet-chi đọc ExpenseRequest
trả 500 UndefinedColumn, trong đó `GET /api/duyet-chi/queue/me` chạy ở sidebar MỌI trang (templates/_header.html)
→ vỡ badge số chờ duyệt + màn Duyệt chi ở mọi app đã nhận shared mới, và ở chat_internal nếu nginx đưa
/api/duyet-chi về đó. Ngược lại shared CŨ chạy trên DB đã có cột thì không sao (cột nullable, ORM cũ không
liệt kê). Downgrade xoá cột — MẤT người nhận / ngày nhận đã ghi trên đề xuất.
"""
from alembic import op
import sqlalchemy as sa


revision = "0050_expense_nguoi_nhan"
down_revision = "0049_expense_chi_tiet"
branch_labels = None
depends_on = None


_COT = (
    ("nguoi_nhan", sa.String(255)),   # người/đơn vị THỰC NHẬN — kế toán ghi lúc bấm Chi
    ("ngay_nhan", sa.Date()),         # ngày bên nhận thực nhận tiền (không ràng buộc ngày chi)
)


def upgrade() -> None:
    for ten, kieu in _COT:
        op.add_column("expense_requests", sa.Column(ten, kieu, nullable=True), schema="shared")


def downgrade() -> None:
    for ten, _ in reversed(_COT):
        op.drop_column("expense_requests", ten, schema="shared")
