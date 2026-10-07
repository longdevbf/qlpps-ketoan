"""shared.mai_preferences — Memory/Preferences cho AI Mai

Mai nhớ chỉ thị của user qua nhiều session (vd "không cần báo cáo cuối tuần",
"tôi quan tâm phòng Kế Toán nhất").

Revision ID: 0025_mai_preferences
Revises: 0024_mai_targets
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa


revision = "0025_mai_preferences"
down_revision = "0024_mai_targets"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")

    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = insp.get_table_names(schema="shared")

    if "mai_preferences" not in existing_tables:
        op.create_table(
            "mai_preferences",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("username", sa.Text(), nullable=False),
            sa.Column("key", sa.Text(), nullable=False),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.UniqueConstraint("user_id", "key", name="uq_mai_preferences_user_key"),
            schema="shared",
        )
        op.create_index(
            "ix_mai_preferences_user_id",
            "mai_preferences",
            ["user_id"],
            schema="shared",
        )
        op.create_index(
            "ix_mai_preferences_username",
            "mai_preferences",
            ["username"],
            schema="shared",
        )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = insp.get_table_names(schema="shared")
    if "mai_preferences" in existing_tables:
        op.drop_index(
            "ix_mai_preferences_username",
            table_name="mai_preferences",
            schema="shared",
        )
        op.drop_index(
            "ix_mai_preferences_user_id",
            table_name="mai_preferences",
            schema="shared",
        )
        op.drop_table("mai_preferences", schema="shared")
