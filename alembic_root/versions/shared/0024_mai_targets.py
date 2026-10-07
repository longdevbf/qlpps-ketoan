"""create shared.mai_targets table — Targets/Goals cho Mai AI

Revision ID: 0024_mai_targets
Revises: 0023_seed_mai_ai_user
Create Date: 2026-05-23

CEO nhập target (doanh thu / leads / đơn hàng / KPI ...) cho company /
department / employee theo period (month/quarter/year). Mai dùng tool
`get_targets` để biết kỳ vọng + đánh giá % đạt.

Idempotent: dùng IF NOT EXISTS — chạy lại không fail.
"""
from alembic import op
import sqlalchemy as sa


revision = "0024_mai_targets"
down_revision = "0023_seed_mai_ai_user"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")
    op.execute("""
        CREATE TABLE IF NOT EXISTS shared.mai_targets (
            id              SERIAL PRIMARY KEY,
            scope           VARCHAR(32)  NOT NULL,
            scope_value     TEXT         NULL,
            metric          TEXT         NOT NULL,
            period_type     VARCHAR(16)  NOT NULL,
            period_value    TEXT         NOT NULL,
            target_value    NUMERIC(15,0) NOT NULL,
            created_by      VARCHAR(64)  NULL,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
    """)
    # Unique key (scope, COALESCE(scope_value,''), metric, period_value)
    # — dùng expression index để NULL scope_value vẫn unique được.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_mai_targets_scope_metric_period
        ON shared.mai_targets (scope, COALESCE(scope_value, ''), metric, period_value)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mai_targets_period_value
        ON shared.mai_targets (period_value)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mai_targets_metric
        ON shared.mai_targets (metric)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS shared.ix_mai_targets_metric")
    op.execute("DROP INDEX IF EXISTS shared.ix_mai_targets_period_value")
    op.execute("DROP INDEX IF EXISTS shared.ux_mai_targets_scope_metric_period")
    op.execute("DROP TABLE IF EXISTS shared.mai_targets")
