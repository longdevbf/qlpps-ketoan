"""calendar_events + event_participants — lịch làm việc cross-app

Revision ID: 0019_calendar_events
Revises: 0018_expense_3step
Create Date: 2026-05-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_calendar_events"
down_revision = "0018_expense_3step"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_username", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_dt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_dt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("all_day", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("event_type", sa.String(16), server_default="personal", nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("color", sa.String(16), nullable=True),
        sa.Column("timezone", sa.String(64), server_default="Asia/Ho_Chi_Minh", nullable=False),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column("source_ref_id", sa.String(64), nullable=True),
        sa.Column("reminder_minutes", sa.Integer(), nullable=True),
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendar_events")),
        schema="shared",
    )
    op.create_index("ix_calendar_events_owner", "calendar_events", ["owner_username"], schema="shared")
    op.create_index("ix_calendar_events_start", "calendar_events", ["start_dt"], schema="shared")
    op.create_index("ix_calendar_events_source", "calendar_events", ["source", "source_ref_id"], schema="shared")

    op.create_table(
        "event_participants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="invited", nullable=False),
        sa.Column("role", sa.String(16), server_default="attendee", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_participants")),
        sa.ForeignKeyConstraint(
            ["event_id"], ["shared.calendar_events.id"],
            name=op.f("fk_event_participants_event_id_calendar_events"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("event_id", "username", name="uq_event_participant"),
        schema="shared",
    )
    op.create_index(
        "ix_event_participants_username", "event_participants", ["username"], schema="shared"
    )


def downgrade():
    op.drop_index("ix_event_participants_username", table_name="event_participants", schema="shared")
    op.drop_table("event_participants", schema="shared")
    op.drop_index("ix_calendar_events_source", table_name="calendar_events", schema="shared")
    op.drop_index("ix_calendar_events_start", table_name="calendar_events", schema="shared")
    op.drop_index("ix_calendar_events_owner", table_name="calendar_events", schema="shared")
    op.drop_table("calendar_events", schema="shared")
