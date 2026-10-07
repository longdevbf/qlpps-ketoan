"""expense_requests: thêm approval_level + approval_history (3-step workflow)

Revision ID: 0018_expense_3step
Revises: 0017_nhanh_config_seed
Create Date: 2026-05-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0018_expense_3step"
down_revision = "0017_nhanh_config_seed"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "expense_requests",
        sa.Column("approval_level", sa.String(16), server_default="manager", nullable=False),
        schema="shared",
    )
    op.add_column(
        "expense_requests",
        sa.Column("approval_history", JSONB, server_default="[]", nullable=False),
        schema="shared",
    )
    op.create_index(
        "ix_expense_requests_approval_level",
        "expense_requests",
        ["approval_level"],
        schema="shared",
    )

    # Backfill row hiện có:
    # trang_thai='cho_duyet' → approval_level='manager' (đang chờ manager duyệt)
    # trang_thai='da_duyet'  → approval_level='done'    (đã hoàn tất chuỗi)
    # trang_thai='tu_choi'   → approval_level='rejected'
    op.execute(
        "UPDATE shared.expense_requests SET approval_level = 'done' "
        "WHERE trang_thai = 'da_duyet'"
    )
    op.execute(
        "UPDATE shared.expense_requests SET approval_level = 'rejected' "
        "WHERE trang_thai = 'tu_choi'"
    )
    # Backfill approval_history từ nguoi_duyet hiện có (1 entry single-step legacy)
    op.execute("""
        UPDATE shared.expense_requests
        SET approval_history = jsonb_build_array(
            jsonb_build_object(
                'level', 'manager',
                'username', nguoi_duyet,
                'ho_ten', COALESCE(ho_ten_nguoi_duyet, nguoi_duyet),
                'action', CASE WHEN trang_thai = 'da_duyet' THEN 'approve' ELSE 'reject' END,
                'comment', COALESCE(nhan_xet_duyet, ''),
                'at', COALESCE(ngay_duyet, updated_at)::text
            )
        )
        WHERE nguoi_duyet IS NOT NULL
    """)


def downgrade():
    op.drop_index("ix_expense_requests_approval_level", table_name="expense_requests", schema="shared")
    op.drop_column("expense_requests", "approval_history", schema="shared")
    op.drop_column("expense_requests", "approval_level", schema="shared")
