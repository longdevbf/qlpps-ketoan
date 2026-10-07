"""morning_brief — bảng chứa AI brief sáng pre-compute mỗi ngày

Revision ID: 0021_morning_brief
Revises: 0020_directive_group_id
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0021_morning_brief"
down_revision = "0020_directive_group_id"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "morning_brief",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("ho_ten", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("phong_ban", sa.String(128), nullable=True),
        sa.Column("brief_date", sa.Date, nullable=False),
        sa.Column("brief_level", sa.String(16), nullable=False),
        sa.Column("metrics", JSONB, server_default="{}", nullable=False),
        sa.Column("alerts", JSONB, server_default="[]", nullable=False),
        sa.Column("highlights", JSONB, server_default="[]", nullable=False),
        sa.Column("content_md", sa.Text, nullable=False),
        sa.Column("model_used", sa.String(64), nullable=True),
        sa.Column("tokens_in", sa.Integer, server_default="0", nullable=False),
        sa.Column("tokens_out", sa.Integer, server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), server_default="0", nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_count", sa.Integer, server_default="0", nullable=False),
        sa.UniqueConstraint("user_id", "brief_date", name="uq_morning_brief_user_date"),
        schema="shared",
    )
    op.create_index(
        "ix_morning_brief_date",
        "morning_brief",
        ["brief_date"],
        schema="shared",
    )
    op.create_index(
        "ix_morning_brief_username",
        "morning_brief",
        ["username"],
        schema="shared",
    )


def downgrade():
    op.drop_index("ix_morning_brief_username", table_name="morning_brief", schema="shared")
    op.drop_index("ix_morning_brief_date", table_name="morning_brief", schema="shared")
    op.drop_table("morning_brief", schema="shared")
