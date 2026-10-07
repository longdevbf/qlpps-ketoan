"""ZNS send log — lưu lịch sử gửi Zalo Notification Service.

Revision ID: 0035_zns_send_log
Revises: 0034_mai_auto_decisions
Create Date: 2026-05-28
"""
from alembic import op


revision = "0035_zns_send_log"
down_revision = "0034_mai_auto_decisions"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")
    op.execute("""
        CREATE TABLE IF NOT EXISTS shared.zns_send_log (
            id              BIGSERIAL PRIMARY KEY,
            ref_type        VARCHAR(32) NOT NULL,
            ref_id          VARCHAR(64) NOT NULL,
            phone           VARCHAR(32) NOT NULL,
            template_id     VARCHAR(64) NOT NULL,
            template_key    VARCHAR(64) NULL,
            params          JSONB NULL,
            status          VARCHAR(20) NOT NULL,
            error_code      INTEGER NULL,
            error_message   TEXT NULL,
            zalo_msg_id     VARCHAR(64) NULL,
            response        JSONB NULL,
            quota_remaining INTEGER NULL,
            triggered_by    VARCHAR(64) NULL,
            sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""CREATE INDEX IF NOT EXISTS ix_zns_ref ON shared.zns_send_log (ref_type, ref_id)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_zns_status_time ON shared.zns_send_log (status, sent_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_zns_phone ON shared.zns_send_log (phone, sent_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_zns_template ON shared.zns_send_log (template_key, sent_at DESC)""")


def downgrade():
    op.execute("DROP INDEX IF EXISTS shared.ix_zns_template")
    op.execute("DROP INDEX IF EXISTS shared.ix_zns_phone")
    op.execute("DROP INDEX IF EXISTS shared.ix_zns_status_time")
    op.execute("DROP INDEX IF EXISTS shared.ix_zns_ref")
    op.execute("DROP TABLE IF EXISTS shared.zns_send_log")
