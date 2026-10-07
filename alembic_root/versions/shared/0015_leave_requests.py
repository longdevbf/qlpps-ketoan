"""create shared.leave_requests table

Revision ID: 0015_leave_requests
Revises: 0014_user_is_on_duty
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_leave_requests"
down_revision = "0014_user_is_on_duty"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")
    op.create_table(
        "leave_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("ho_ten", sa.String(128), nullable=False),
        sa.Column("phong_ban", sa.String(128), nullable=True),
        sa.Column("app_name", sa.String(32), nullable=False),
        sa.Column("loai_nghi", sa.String(64), nullable=False),
        sa.Column("ngay_bat_dau", sa.Date(), nullable=False),
        sa.Column("ngay_ket_thuc", sa.Date(), nullable=False),
        sa.Column("buoi", sa.String(16), server_default="ca_ngay", nullable=False),
        sa.Column("so_ngay", sa.Numeric(4, 1), server_default="1", nullable=False),
        sa.Column("ly_do", sa.Text(), nullable=False),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("trang_thai", sa.String(32), server_default="cho_duyet", nullable=False),
        sa.Column("nguoi_duyet", sa.String(64), nullable=True),
        sa.Column("ho_ten_nguoi_duyet", sa.String(128), nullable=True),
        sa.Column("nhan_xet_duyet", sa.Text(), nullable=True),
        sa.Column("ngay_duyet", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leave_requests")),
        schema="shared",
    )
    op.create_index("ix_leave_requests_username", "leave_requests", ["username"], schema="shared")
    op.create_index("ix_leave_requests_trang_thai", "leave_requests", ["trang_thai"], schema="shared")
    op.create_index("ix_leave_requests_ngay", "leave_requests", ["ngay_bat_dau"], schema="shared")


def downgrade():
    op.drop_index("ix_leave_requests_ngay", table_name="leave_requests", schema="shared")
    op.drop_index("ix_leave_requests_trang_thai", table_name="leave_requests", schema="shared")
    op.drop_index("ix_leave_requests_username", table_name="leave_requests", schema="shared")
    op.drop_table("leave_requests", schema="shared")
