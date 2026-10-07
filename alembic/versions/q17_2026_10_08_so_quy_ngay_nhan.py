"""so_quy: thêm cột ngay_nhan — ngày bên nhận THỰC NHẬN tiền, kế toán ghi ở hộp "Chi tiền và ghi sổ" (Việc 3).

Hộp chi tiền ở màn Duyệt chi (/ketoan/kt-duyet) nay cho kế toán ghi người nhận + ngày nhận trước khi ghi sổ, ở
cả 3 cửa chi (Đề xuất chi, Đề nghị TT, Trả NCC). Người nhận dùng cột có sẵn `so_quy.doi_tuong_ten` (q14); ngày
nhận chưa có chỗ chứa nên thêm cột này. Ngày nhận chỉ để GHI NHẬN — ngày ghi sổ vẫn là `so_quy.ngay` (chuyển
khoản liên ngân hàng có thể nhận muộn hơn ngày tiền rời tài khoản mình).

Một cột DATE NULLABLE, không default, KHÔNG backfill: mọi dòng cũ giữ NULL. Cột nullable không default →
PostgreSQL chỉ sửa danh mục hệ thống, không ghi lại bảng.

THỨ TỰ BẮT BUỘC khi lên production: chạy migration này (và 0050 của schema shared, alembic_root) TRƯỚC khi
container nào chạy code mới. ORM liệt kê MỌI cột của model trong cả SELECT lẫn INSERT (cùng kiểu lỗi cột
ref_sepay ghi trong CLAUDE.md) → code mới gặp DB chưa có cột sẽ lỗi UndefinedColumn ở MỌI chỗ đọc/ghi SoQuy
qua ORM (21 file trong app/ dùng model SoQuy: Sổ quỹ, Ngân hàng, cầu nối doanh thu / chi phí / công nợ / SePay,
báo cáo dòng tiền…). Chỗ NGUY HIỂM NHẤT hỏng ÂM THẦM: nút Chi của Đề nghị TT — cầu nối
`sync_so_quy_chi_phi_from_denghitt` là fail-soft (lỗi thì rollback savepoint rồi trả về bình thường), router
vẫn đánh dấu da_chi → khoản được đánh dấu ĐÃ CHI mà KHÔNG có phiếu sổ quỹ; lỡ chạy sai thứ tự thì phải đối soát
tay các Đề nghị TT chi trong khoảng đó (chạy migration xong không tự sinh lại phiếu).
Ngược lại code CŨ chạy trên DB đã có cột thì không sao (cột nullable, code cũ không liệt kê nó).
Downgrade xoá cột — MẤT ngày nhận đã ghi.

Revision ID: q17_2026_10_08_so_quy_ngay_nhan
Revises: q16_2026_10_07_nguoi_nop
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "q17_2026_10_08_so_quy_ngay_nhan"
down_revision: Union[str, None] = "q16_2026_10_07_nguoi_nop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "so_quy",
        sa.Column("ngay_nhan", sa.Date(), nullable=True),
        schema="ketoan",
    )


def downgrade() -> None:
    op.drop_column("so_quy", "ngay_nhan", schema="ketoan")
