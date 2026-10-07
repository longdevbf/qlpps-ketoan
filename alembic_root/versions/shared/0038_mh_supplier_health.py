"""shared.mh_supplier_health — cache điểm NCC tính bởi mh_supplier_health_score.

Revision ID: 0038_mh_supplier_health
Revises: 0037_mai_mh_features
Create Date: 2026-06-16

Anh Quang 2026-06-16 — Wave 2D. Bảng cache point health của NCC, scheduler
job mh_supplier_health_score chạy 5h sáng UPSERT row theo supplier_id
(unique). Mai dùng để báo cáo Top/Bottom NCC + Leader xem dashboard.

Cột raw JSONB lưu chi tiết từng sub-score (n_samples, on_time count,
avg_response_minutes, issues count) để debug khi score lạ.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0038_mh_supplier_health"
down_revision = "0037_mai_mh_features"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mh_supplier_health",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("supplier_id", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("score_total", sa.Numeric(5, 2)),
        sa.Column("score_price", sa.Numeric(5, 2)),
        sa.Column("score_ontime", sa.Numeric(5, 2)),
        sa.Column("score_response", sa.Numeric(5, 2)),
        sa.Column("score_quality", sa.Numeric(5, 2)),
        sa.Column("raw", postgresql.JSONB),
        schema="shared",
    )
    op.create_index(
        "ix_mh_score_total",
        "mh_supplier_health",
        ["score_total"],
        schema="shared",
    )


def downgrade():
    op.drop_index("ix_mh_score_total", "mh_supplier_health", schema="shared")
    op.drop_table("mh_supplier_health", schema="shared")
