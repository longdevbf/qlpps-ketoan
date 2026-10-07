"""shared.notifications — bảng noti dùng chung 3 app.

Pattern fan-out: 1 row/user. Index theo (target_username, seen, created_at).

Revision ID: 0012_notifications
Revises: 0011_addon_cach_tinh
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_notifications"
down_revision: Union[str, None] = "0011_addon_cach_tinh"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("target_username", sa.String(64), nullable=False),
        sa.Column("source_app", sa.String(16), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text),
        sa.Column("ref_type", sa.String(32)),
        sa.Column("ref_id", sa.String(64)),
        sa.Column("url", sa.String(512)),
        sa.Column("severity", sa.String(16), nullable=False, server_default="info"),
        sa.Column("seen", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("seen_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(64)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="shared",
    )
    op.create_index(
        "ix_noti_target_seen_created",
        "notifications",
        ["target_username", "seen", "created_at"],
        schema="shared",
    )
    op.create_index(
        "ix_noti_ref",
        "notifications",
        ["ref_type", "ref_id"],
        schema="shared",
    )


def downgrade() -> None:
    op.drop_index("ix_noti_ref", "notifications", schema="shared")
    op.drop_index("ix_noti_target_seen_created", "notifications", schema="shared")
    op.drop_table("notifications", schema="shared")
