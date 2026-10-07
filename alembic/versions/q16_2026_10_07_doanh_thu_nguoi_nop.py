"""doanh_thu: thêm cột nguoi_nop (người nộp tiền) cho hộp "Ghi nhận doanh thu" ở /ketoan/thu-chi.

Hộp ghi doanh thu chưa có chỗ ghi AI nộp tiền: bảng chỉ có nv_kinh_doanh (nhân viên được tính
doanh số) và ma_don — phiếu không gắn đơn thì không biết tiền của ai, phiếu có đơn thì phải tra
sang Báo giá mới biết khách.

Một cột VARCHAR(128) NULLABLE, không default, KHÔNG backfill: mọi dòng cũ giữ NULL (tên khách của
dòng có mã đơn vẫn xem được ở popup chi tiết, đọc từ baogia.quotes). Cột nullable không default →
PostgreSQL chỉ sửa danh mục hệ thống, không ghi lại bảng.

THỨ TỰ BẮT BUỘC khi lên production: chạy migration này TRƯỚC khi khởi động lại container chạy code
mới. `select(DoanhThu)` liệt kê MỌI cột của model → code mới gặp DB chưa có cột sẽ trả 500
UndefinedColumn ở GET /api/doanh-thu (cùng kiểu lỗi cột ref_sepay của so_quy ghi trong CLAUDE.md).
Downgrade xoá cột — MẤT tên người nộp đã nhập.

Revision ID: q16_2026_10_07_nguoi_nop
Revises: q15_2026_10_01
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "q16_2026_10_07_nguoi_nop"
down_revision: Union[str, None] = "q15_2026_10_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "doanh_thu",
        sa.Column("nguoi_nop", sa.String(128), nullable=True),
        schema="ketoan",
    )


def downgrade() -> None:
    op.drop_column("doanh_thu", "nguoi_nop", schema="ketoan")
