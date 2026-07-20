"""add breakdown helper tables (so_du_dau_ky, bao_cao_snapshot)

NOTE: spec ban đầu yêu cầu revision="0002_add_fields_breakdown" + nhiều ALTER
add column (quy/phong_ban/nguoi_chi/don_vi_vc/loai_thanh_toan/lap_lai). Sau khi
kiểm tra `0001_baseline_ketoan.py`, các cột này ĐÃ tồn tại trong baseline →
không cần ALTER. Đồng thời `0002_doanh_thu_ref_order` đã tồn tại nên migration
này chain sau (0003) để giữ history tuyến tính, tránh branch heads.

Tóm lại migration này CHỈ tạo 2 bảng mới:
    - ketoan.so_du_dau_ky    (số dư đầu kỳ theo tháng × tài khoản)
    - ketoan.bao_cao_snapshot (snapshot P&L theo tháng, JSONB)

Revision ID: 0003_add_breakdown_tables
Revises: 0002_doanh_thu_ref_order
Create Date: 2026-04-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0003_add_breakdown_tables"
down_revision: Union[str, None] = "0002_doanh_thu_ref_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----------------- so_du_dau_ky -----------------
    op.create_table(
        "so_du_dau_ky",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thang", sa.Date(), nullable=False),  # yyyy-mm-01
        sa.Column(
            "tai_khoan_id",
            sa.Integer(),
            sa.ForeignKey("ketoan.tai_khoan_nh.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("so_du", sa.Numeric(15, 2), server_default="0", nullable=False),
        sa.Column("ghi_chu", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("thang", "tai_khoan_id", name="uq_sddk_thang_tk"),
        schema="ketoan",
    )
    op.create_index(
        "ix_sddk_thang",
        "so_du_dau_ky",
        [sa.text("thang DESC")],
        schema="ketoan",
    )

    # ----------------- bao_cao_snapshot -----------------
    op.create_table(
        "bao_cao_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thang", sa.Date(), nullable=False, unique=True),  # yyyy-mm-01
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", sa.Text()),
        schema="ketoan",
    )


def downgrade() -> None:
    op.drop_table("bao_cao_snapshot", schema="ketoan")
    op.drop_index("ix_sddk_thang", table_name="so_du_dau_ky", schema="ketoan")
    op.drop_table("so_du_dau_ky", schema="ketoan")
