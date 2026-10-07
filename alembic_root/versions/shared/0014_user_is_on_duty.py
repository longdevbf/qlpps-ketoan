"""shared.users.is_on_duty — KD/manager toggle on-duty.

KD bán lẻ và manager có nút On/Off ở header baogia. Khi off → MKT chuyển
lead sẽ KHÔNG thấy user trong dropdown.

Default TRUE (user hiện tại = đang on-duty), backfill = TRUE.

Revision ID: 0014_user_is_on_duty
Revises: 0013_push_subscriptions
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_user_is_on_duty"
down_revision: Union[str, None] = "0013_push_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_on_duty",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        schema="shared",
    )


def downgrade() -> None:
    op.drop_column("users", "is_on_duty", schema="shared")
