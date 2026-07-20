"""Phase 5C P&L — phương pháp phân bổ chi phí (enum).

Thêm cột `phuong_phap_phan_bo` (enum) + `phan_bo_manual` (JSONB) cho
`ketoan.chi_phi_co_dinh` để hỗ trợ 6 phương pháp phân bổ:

  - duong_thang        : chia đều theo tháng (5A — default, legacy compat)
  - prorated_by_day    : chia theo ngày (5B)
  - front_loaded       : đầu nặng đuôi nhẹ (50% T1, 50% chia đều các tháng còn lại)
  - seasonal           : trọng số mùa Tết (T11/T12/T01/T02 = 60%; T03..T10 = 40%/8)
  - by_revenue_pct     : theo % doanh thu thực hiện (so_tien_thang = % vd 5)
  - manual             : nhập tay tỷ lệ % cho 12 tháng qua JSONB
                         {"01": 10, "02": 5, ..., "12": 15}  (đơn vị %)
                         hoặc {"YYYY-MM": pct} cho phân bổ cụ thể.

Backfill: tất cả dòng cũ → 'duong_thang' (qua DEFAULT) — không phá legacy.

Revision ID: p5c_2026_04_29
Revises: p5b_2026_04_29  (placeholder — em rebase nếu cần)
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "p5c_2026_04_29"
down_revision: Union[str, None] = "p5b_2026_04_29"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Cột phuong_phap_phan_bo VARCHAR(20) NOT NULL DEFAULT 'duong_thang'
    op.add_column(
        "chi_phi_co_dinh",
        sa.Column(
            "phuong_phap_phan_bo",
            sa.String(length=20),
            server_default="duong_thang",
            nullable=False,
        ),
        schema="ketoan",
    )

    # 2) Cột phan_bo_manual JSONB nullable
    op.add_column(
        "chi_phi_co_dinh",
        sa.Column(
            "phan_bo_manual",
            JSONB(),
            nullable=True,
        ),
        schema="ketoan",
    )

    # 3) CHECK constraint enum
    op.create_check_constraint(
        "ck_cpcd_method",
        "chi_phi_co_dinh",
        (
            "phuong_phap_phan_bo IN ("
            "'duong_thang','prorated_by_day','front_loaded',"
            "'seasonal','by_revenue_pct','manual')"
        ),
        schema="ketoan",
    )

    # 4) Index trên method để filter nhanh
    op.create_index(
        "ix_cpcd_method",
        "chi_phi_co_dinh",
        ["phuong_phap_phan_bo"],
        schema="ketoan",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cpcd_method",
        table_name="chi_phi_co_dinh",
        schema="ketoan",
    )
    op.drop_constraint(
        "ck_cpcd_method",
        "chi_phi_co_dinh",
        schema="ketoan",
        type_="check",
    )
    op.drop_column(
        "chi_phi_co_dinh",
        "phan_bo_manual",
        schema="ketoan",
    )
    op.drop_column(
        "chi_phi_co_dinh",
        "phuong_phap_phan_bo",
        schema="ketoan",
    )
