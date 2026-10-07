"""Expense Request — đa file chứng từ (JSONB array).

Revision ID: 0037_expense_chung_tu_urls
Revises: 0036_mai_kd_features
Create Date: 2026-06-15

User yêu cầu: đề xuất chi cho upload nhiều ảnh (hiện chỉ 1).
Thay vì refactor sang bảng attachment riêng (heavyweight), thêm cột
`chung_tu_urls JSONB DEFAULT '[]'` lưu list URL. Giữ `chung_tu_url` cũ
cho backward-compat (sync = phần tử đầu của list khi có).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0037_expense_chung_tu_urls"
down_revision = "0036_mai_kd_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "expense_requests",
        sa.Column(
            "chung_tu_urls",
            JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        schema="shared",
    )
    # Backfill: nếu row có chung_tu_url cũ → đẩy vào list
    op.execute(
        "UPDATE shared.expense_requests "
        "SET chung_tu_urls = jsonb_build_array(chung_tu_url) "
        "WHERE chung_tu_url IS NOT NULL AND chung_tu_url <> ''"
    )


def downgrade() -> None:
    op.drop_column("expense_requests", "chung_tu_urls", schema="shared")
