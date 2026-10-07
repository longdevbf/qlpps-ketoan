"""shared.push_subscriptions — Web Push subscription per device.

Revision ID: 0013_push_subscriptions
Revises: 0012_notifications
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013_push_subscriptions"
down_revision: Union[str, None] = "0012_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("endpoint", sa.Text, nullable=False),
        sa.Column("p256dh", sa.String(255), nullable=False),
        sa.Column("auth", sa.String(255), nullable=False),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("source_app", sa.String(16)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("endpoint", name="uq_push_sub_endpoint"),
        schema="shared",
    )
    op.create_index(
        "ix_push_sub_username",
        "push_subscriptions",
        ["username"],
        schema="shared",
    )


def downgrade() -> None:
    op.drop_index("ix_push_sub_username", "push_subscriptions", schema="shared")
    op.drop_table("push_subscriptions", schema="shared")
