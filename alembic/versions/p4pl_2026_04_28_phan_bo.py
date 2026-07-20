"""Phase 4 P&L — phân bổ định phí (so_thang_phan_bo).

Thêm cột `so_thang_phan_bo` cho `ketoan.chi_phi_co_dinh` để hỗ trợ phân bổ
định phí trả 1 lần cho nhiều tháng (vd thuê VP 12 tháng).

Quy tắc P&L:
  - so_thang_phan_bo = 1 (default): chi phí ghi nhận đầy đủ trong tháng `thang_bat_dau`
    HOẶC nếu lap_lai=True thì hàng tháng kể từ `thang_bat_dau`.
  - so_thang_phan_bo > 1: chi phí được phân bổ đều `so_tien_thang / so_thang_phan_bo`
    cho mỗi tháng từ `thang_bat_dau` đến `thang_bat_dau + so_thang_phan_bo - 1`.

Backfill: tất cả dòng cũ → so_thang_phan_bo = 1 (qua DEFAULT).

Revision ID: p4pl_2026_04_28
Revises: p3tscd_2026_04_28
Create Date: 2026-04-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p4pl_2026_04_28"
down_revision: Union[str, None] = "p3tscd_2026_04_28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chi_phi_co_dinh",
        sa.Column(
            "so_thang_phan_bo",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        schema="ketoan",
    )
    # CHECK constraint: ≥ 1
    op.create_check_constraint(
        "ck_cpcd_so_thang_phan_bo_pos",
        "chi_phi_co_dinh",
        "so_thang_phan_bo >= 1",
        schema="ketoan",
    )
    # Partial index — chỉ index các dòng phân bổ đa kỳ (tối ưu storage)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_cpcd_thang_phan_bo
        ON ketoan.chi_phi_co_dinh (so_thang_phan_bo)
        WHERE so_thang_phan_bo > 1
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ketoan.ix_cpcd_thang_phan_bo")
    op.drop_constraint(
        "ck_cpcd_so_thang_phan_bo_pos",
        "chi_phi_co_dinh",
        schema="ketoan",
        type_="check",
    )
    op.drop_column(
        "chi_phi_co_dinh",
        "so_thang_phan_bo",
        schema="ketoan",
    )
