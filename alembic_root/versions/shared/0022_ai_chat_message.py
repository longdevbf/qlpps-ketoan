"""ai_chat_message — lịch sử chat giữa user và AI Mai

Revision ID: 0022_ai_chat_message
Revises: 0021_morning_brief
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa


revision = "0022_ai_chat_message"
down_revision = "0021_morning_brief"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_chat_message",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        # role: 'user' (NV/CEO hỏi) | 'assistant' (Mai trả lời)
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("brief_level", sa.String(16), nullable=False),
        sa.Column("model_used", sa.String(64), nullable=True),
        sa.Column("tokens_in", sa.Integer, server_default="0", nullable=False),
        sa.Column("tokens_out", sa.Integer, server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="shared",
    )
    op.create_index(
        "ix_ai_chat_user_time",
        "ai_chat_message",
        ["user_id", "created_at"],
        schema="shared",
    )


def downgrade():
    op.drop_index("ix_ai_chat_user_time", table_name="ai_chat_message", schema="shared")
    op.drop_table("ai_chat_message", schema="shared")
