"""baseline shared schema (users, audit_log, sessions, app_config)

Revision ID: 0001_baseline_shared
Revises:
Create Date: 2026-04-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_baseline_shared"
down_revision: Union[str, None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Schema đã được container init script tạo, nhưng safe-guard idempotent
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")
    op.execute("CREATE SCHEMA IF NOT EXISTS baogia")
    op.execute("CREATE SCHEMA IF NOT EXISTS marketing")
    op.execute("CREATE SCHEMA IF NOT EXISTS muahang")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "unaccent"')

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), unique=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(128), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("apps", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("phone", sa.String(32)),
        sa.Column("avatar_url", sa.String(512)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="shared",
    )
    op.create_index("ix_users_role", "users", ["role"], schema="shared")

    # audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("app", sa.String(32), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("shared.users.id")),
        sa.Column("username", sa.String(64)),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource", sa.String(255)),
        sa.Column("ip", postgresql.INET()),
        sa.Column("ua", sa.String(512)),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("status", sa.String(16), server_default="ok", nullable=False),
        schema="shared",
    )
    op.create_index("ix_audit_ts", "audit_log", ["ts"], schema="shared")
    op.create_index("ix_audit_user_ts", "audit_log", ["user_id", "ts"], schema="shared")
    op.create_index("ix_audit_action", "audit_log", ["action"], schema="shared")
    op.create_index("ix_audit_app", "audit_log", ["app"], schema="shared")

    # sessions (refresh token tracking)
    op.create_table(
        "sessions",
        sa.Column("jti", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("shared.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("ip", postgresql.INET()),
        sa.Column("ua", sa.String(512)),
        schema="shared",
    )
    op.create_index("ix_sessions_user", "sessions", ["user_id"], schema="shared")
    op.create_index("ix_sessions_expires", "sessions", ["expires_at"], schema="shared")

    # app_config
    op.create_table(
        "app_config",
        sa.Column("app", sa.String(32), primary_key=True),
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", postgresql.JSONB()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("shared.users.id")),
        schema="shared",
    )


def downgrade() -> None:
    op.drop_table("app_config", schema="shared")
    op.drop_table("sessions", schema="shared")
    op.drop_table("audit_log", schema="shared")
    op.drop_table("users", schema="shared")
