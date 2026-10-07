"""doanh_thu: thêm cột nguoi_nop (người nộp tiền) cho hộp "Ghi nhận doanh thu" ở /ketoan/thu-chi.

Hộp ghi doanh thu chưa có chỗ ghi AI nộp tiền: bảng chỉ có nv_kinh_doanh (nhân viên được tính
doanh số) và ma_don — phiếu không gắn đơn thì không biết tiền của ai, phiếu có đơn thì phải tra
sang Báo giá mới biết khách.

Một cột VARCHAR(128) NULLABLE, không default, KHÔNG backfill: mọi dòng cũ giữ NULL (tên khách của
dòng có mã đơn vẫn xem được ở popup chi tiết, đọc từ baogia.quotes). Cột nullable không default →
PostgreSQL chỉ sửa danh mục hệ thống, không ghi lại bảng.

THỨ TỰ BẮT BUỘC khi lên production: chạy migration này TRƯỚC khi container chạy code mới. ORM liệt kê
MỌI cột của model trong cả SELECT lẫn INSERT → code mới gặp DB chưa có cột sẽ lỗi UndefinedColumn ở
MỌI chỗ đọc/ghi DoanhThu qua ORM (cùng kiểu lỗi cột ref_sepay của so_quy ghi trong CLAUDE.md):
  đọc — danh sách / chi tiết / sửa / xoá doanh thu (routers/doanh_thu.py), Duyệt cọc (kt_duyet.py),
        tải chứng từ doanh thu (uploads.py), bridge doanh thu từ PO (services/revenue_from_order.py);
  ghi — Ghi nhận doanh thu, Duyệt cọc, cọc bổ sung (coc_bo_sung.py), bridge PO, và bấm Hoàn thành vận
        chuyển có thu tiền (external.py — db.flush() không nằm trong try → cả thao tác trả lỗi).
        RIÊNG Duyệt cọc hỏng ÂM THẦM: báo giá được duyệt + commit trước, phần ghi doanh thu cọc lỗi thì
        rollback và chỉ log WARNING (kt_duyet.py), tin nhắn nhóm vẫn báo "đã vào sổ quỹ" — lỡ chạy sai thứ
        tự thì phải đối soát tay các đơn được duyệt cọc trong khoảng đó (chạy migration xong không tự sinh lại).
Ngược lại code CŨ chạy trên DB đã có cột thì không sao (cột nullable, code cũ không liệt kê nó).
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
