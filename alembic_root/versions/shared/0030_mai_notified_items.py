"""Mai Notified Items — log Mai đã DM NV về 1 đơn pending (chỉ 1 lần/đơn).

Revision ID: 0030_mai_notified_items
Revises: 0029_mai_policy_category
Create Date: 2026-05-23

Bảng `shared.mai_notified_items` lưu lịch sử Mai đã chủ động DM NV về đơn
duyệt mới (auto_approve / escalate). Dùng UNIQUE (item_source, item_ref_id)
để đảm bảo mỗi đơn chỉ được Mai DM 1 lần — scheduler tick mỗi 30s sẽ tự
filter ra đơn chưa từng notify.

Idempotent (CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS).
"""
from alembic import op


revision = "0030_mai_notified_items"
down_revision = "0029_mai_policy_category"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")

    op.execute("""
        CREATE TABLE IF NOT EXISTS shared.mai_notified_items (
            id                     BIGSERIAL PRIMARY KEY,
            item_source            VARCHAR(32) NOT NULL,
            item_ref_id            VARCHAR(64) NOT NULL,
            decision               VARCHAR(16) NOT NULL,
            requested_by_username  VARCHAR(64) NULL,
            dm_room_id             INTEGER NULL,
            dm_message_id          BIGINT NULL,
            notified_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ux_mai_notified_items_src_ref
                UNIQUE (item_source, item_ref_id)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mai_notified_source
            ON shared.mai_notified_items (item_source)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS shared.ix_mai_notified_source")
    op.execute("DROP TABLE IF EXISTS shared.mai_notified_items")
