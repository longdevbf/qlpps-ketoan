"""directive group_id — gom batch giao nhiều NV thành 1 thẻ ở UI

Revision ID: 0020_directive_group_id
Revises: 0019_calendar_events
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_directive_group_id"
down_revision = "0019_calendar_events"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "directives",
        sa.Column("group_id", sa.String(32), nullable=True),
        schema="shared",
    )
    op.create_index(
        "ix_directives_group",
        "directives",
        ["group_id"],
        schema="shared",
    )


def downgrade():
    op.drop_index("ix_directives_group", table_name="directives", schema="shared")
    op.drop_column("directives", "group_id", schema="shared")
