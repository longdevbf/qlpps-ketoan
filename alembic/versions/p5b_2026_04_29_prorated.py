"""Phase 5B P&L — prorated chi phí cố định theo ngày.

Thêm cột `ngay_bat_dau` (NOT NULL) + `ngay_ket_thuc` (NULL) cho
`ketoan.chi_phi_co_dinh` để hỗ trợ phân bổ chính xác theo ngày
(vd thuê VP từ 15/03 → tháng 3 chỉ tính 17/30 thay vì full).

Backfill: `ngay_bat_dau = thang_bat_dau` (đã là 1/M/Y).

Quy ước Phase 5B:
  - `ngay_bat_dau` chính xác hơn `thang_bat_dau` (giữ legacy compat)
  - `ngay_ket_thuc` NULL = vô thời hạn (kết hợp với lap_lai=true)
  - Khi tính P&L tháng X: so_tien_thang × overlap_days / 30
    (Vd thuê 15/3/2026 → 31/3 = 17 ngày → 17/30 × so_tien_thang)

Revision ID: p5b_2026_04_29
Revises: p4pl_2026_04_28
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p5b_2026_04_29"
down_revision: Union[str, None] = "p4pl_2026_04_28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Thêm cột nullable trước (cho phép backfill)
    op.add_column(
        "chi_phi_co_dinh",
        sa.Column("ngay_bat_dau", sa.Date(), nullable=True),
        schema="ketoan",
    )
    op.add_column(
        "chi_phi_co_dinh",
        sa.Column("ngay_ket_thuc", sa.Date(), nullable=True),
        schema="ketoan",
    )

    # 2) Backfill: ngay_bat_dau = thang_bat_dau
    op.execute(
        """
        UPDATE ketoan.chi_phi_co_dinh
        SET ngay_bat_dau = thang_bat_dau
        WHERE ngay_bat_dau IS NULL
        """
    )

    # 3) NOT NULL sau khi backfill
    op.alter_column(
        "chi_phi_co_dinh",
        "ngay_bat_dau",
        existing_type=sa.Date(),
        nullable=False,
        schema="ketoan",
    )

    # 4) CHECK constraint: ngay_ket_thuc >= ngay_bat_dau (nếu có)
    op.create_check_constraint(
        "ck_cpcd_ngay",
        "chi_phi_co_dinh",
        "ngay_ket_thuc IS NULL OR ngay_ket_thuc >= ngay_bat_dau",
        schema="ketoan",
    )

    # 5) Index trên ngay_bat_dau
    op.create_index(
        "ix_cpcd_ngay_bat_dau",
        "chi_phi_co_dinh",
        ["ngay_bat_dau"],
        schema="ketoan",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cpcd_ngay_bat_dau",
        table_name="chi_phi_co_dinh",
        schema="ketoan",
    )
    op.drop_constraint(
        "ck_cpcd_ngay",
        "chi_phi_co_dinh",
        schema="ketoan",
        type_="check",
    )
    op.drop_column(
        "chi_phi_co_dinh",
        "ngay_ket_thuc",
        schema="ketoan",
    )
    op.drop_column(
        "chi_phi_co_dinh",
        "ngay_bat_dau",
        schema="ketoan",
    )
