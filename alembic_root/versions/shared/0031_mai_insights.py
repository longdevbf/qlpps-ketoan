"""Mai Insights — log per-NV Mai interactions + activity actions.

Revision ID: 0031_mai_insights
Revises: 0030_mai_notified_items
Create Date: 2026-05-26

Hai bảng:
  1. `shared.mai_interaction` — mỗi lượt Mai trả lời enrich category/intent/tools/outcome.
  2. `shared.nv_activity`     — log hành động chính của NV (PO, expense, leave, directive…).
"""
from alembic import op


revision = "0031_mai_insights"
down_revision = "0030_mai_notified_items"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")

    op.execute("""
        CREATE TABLE IF NOT EXISTS shared.mai_interaction (
            id              BIGSERIAL PRIMARY KEY,
            username        VARCHAR(64) NOT NULL,
            room_id         INTEGER NULL,
            chat_message_id BIGINT NULL,
            category        VARCHAR(32) NULL,    -- data_query|task_create|approval|casual|help|refusal|other
            intent          VARCHAR(64) NULL,    -- vd 'check_revenue','list_po_pending'
            tools_used      TEXT[] NULL,
            tokens_in       INTEGER NULL,
            tokens_out      INTEGER NULL,
            cost_usd        NUMERIC(10,5) NULL,
            outcome         VARCHAR(32) NULL,    -- answered|refused_scope|error|escalated|tool_exec
            duration_ms     INTEGER NULL,
            satisfaction    VARCHAR(16) NULL,    -- positive|negative (auto-detect, có thể NULL)
            metadata        JSONB NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_inter_user_time
                  ON shared.mai_interaction (username, created_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_inter_category
                  ON shared.mai_interaction (category, created_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_inter_created
                  ON shared.mai_interaction (created_at DESC)""")

    op.execute("""
        CREATE TABLE IF NOT EXISTS shared.nv_activity (
            id          BIGSERIAL PRIMARY KEY,
            username    VARCHAR(64) NOT NULL,
            action      VARCHAR(64) NOT NULL,  -- po_create|po_approve|quote_create|expense_submit|leave_submit|directive_create|mai_chat|login
            app         VARCHAR(32) NULL,      -- baogia|muahang|hcns|...
            ref_type    VARCHAR(32) NULL,
            ref_id      VARCHAR(64) NULL,
            metadata    JSONB NULL,
            duration_ms INTEGER NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""CREATE INDEX IF NOT EXISTS ix_nv_activity_user_time
                  ON shared.nv_activity (username, created_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_nv_activity_action
                  ON shared.nv_activity (action, created_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_nv_activity_created
                  ON shared.nv_activity (created_at DESC)""")


def downgrade():
    op.execute("DROP INDEX IF EXISTS shared.ix_nv_activity_created")
    op.execute("DROP INDEX IF EXISTS shared.ix_nv_activity_action")
    op.execute("DROP INDEX IF EXISTS shared.ix_nv_activity_user_time")
    op.execute("DROP TABLE IF EXISTS shared.nv_activity")
    op.execute("DROP INDEX IF EXISTS shared.ix_mai_inter_created")
    op.execute("DROP INDEX IF EXISTS shared.ix_mai_inter_category")
    op.execute("DROP INDEX IF EXISTS shared.ix_mai_inter_user_time")
    op.execute("DROP TABLE IF EXISTS shared.mai_interaction")
