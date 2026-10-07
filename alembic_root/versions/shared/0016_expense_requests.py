"""create shared.expense_requests table

Revision ID: 0016_expense_requests
Revises: 0015_leave_requests
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_expense_requests"
down_revision = "0015_leave_requests"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")
    op.create_table(
        "expense_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("ho_ten", sa.String(128), nullable=False),
        sa.Column("phong_ban", sa.String(128), nullable=True),
        sa.Column("app_name", sa.String(32), nullable=False),
        sa.Column("tieu_de", sa.String(256), nullable=False),
        sa.Column("loai_chi", sa.String(64), nullable=False),
        sa.Column("so_tien", sa.Numeric(15, 0), nullable=False),
        sa.Column("ngay_de_xuat", sa.Date(), nullable=False),
        sa.Column("han_thanh_toan", sa.Date(), nullable=True),
        sa.Column("muc_dich", sa.Text(), nullable=False),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("chung_tu_url", sa.Text(), nullable=True),
        sa.Column("trang_thai", sa.String(32), server_default="cho_duyet", nullable=False),
        sa.Column("nguoi_duyet", sa.String(64), nullable=True),
        sa.Column("ho_ten_nguoi_duyet", sa.String(128), nullable=True),
        sa.Column("nhan_xet_duyet", sa.Text(), nullable=True),
        sa.Column("ngay_duyet", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_expense_requests")),
        schema="shared",
    )
    op.create_index("ix_expense_requests_username", "expense_requests", ["username"], schema="shared")
    op.create_index("ix_expense_requests_trang_thai", "expense_requests", ["trang_thai"], schema="shared")
    op.create_index("ix_expense_requests_ngay", "expense_requests", ["ngay_de_xuat"], schema="shared")


def downgrade():
    op.drop_index("ix_expense_requests_ngay", table_name="expense_requests", schema="shared")
    op.drop_index("ix_expense_requests_trang_thai", table_name="expense_requests", schema="shared")
    op.drop_index("ix_expense_requests_username", table_name="expense_requests", schema="shared")
    op.drop_table("expense_requests", schema="shared")
