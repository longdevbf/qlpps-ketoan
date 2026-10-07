"""create shared.mai_proposals — Mai đề xuất việc, CEO duyệt (Mode B).

Revision ID: 0028_mai_proposals
Revises: 0027_mai_policy_scope
Create Date: 2026-05-23

Mode B workflow (Mai đề xuất → CEO chốt):
- Mai phân tích data → tạo 1 proposal (status='pending') với rationale + list items.
- CEO mở UI / hỏi Mai → /decide → approve | partial | reject.
- Tool layer (không phải migration này) sẽ execute từng item sau khi duyệt
  (vd: tạo Directive, tạo Approval, ...) và update executed_results.

Idempotent: CREATE TABLE/INDEX IF NOT EXISTS — chạy lại không fail. Không seed.
"""
from alembic import op


revision = "0028_mai_proposals"
down_revision = "0027_mai_policy_scope"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")
    op.execute("""
        CREATE TABLE IF NOT EXISTS shared.mai_proposals (
            id                BIGSERIAL PRIMARY KEY,
            user_id           INTEGER       NOT NULL,
            username          VARCHAR(64)   NOT NULL,
            proposal_type     VARCHAR(32)   NOT NULL DEFAULT 'directive',
            title             VARCHAR(255)  NOT NULL,
            rationale         TEXT          NULL,
            items             JSONB         NOT NULL DEFAULT '[]'::jsonb,
            status            VARCHAR(16)   NOT NULL DEFAULT 'pending',
            approved_by       VARCHAR(64)   NULL,
            approved_at       TIMESTAMPTZ   NULL,
            accepted_ids      INTEGER[]     NULL,
            executed_results  JSONB         NULL,
            executed_at       TIMESTAMPTZ   NULL,
            rejection_reason  TEXT          NULL,
            created_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ   NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mai_proposals_user_status
        ON shared.mai_proposals (user_id, status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mai_proposals_status
        ON shared.mai_proposals (status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mai_proposals_type
        ON shared.mai_proposals (proposal_type)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS shared.ix_mai_proposals_type")
    op.execute("DROP INDEX IF EXISTS shared.ix_mai_proposals_status")
    op.execute("DROP INDEX IF EXISTS shared.ix_mai_proposals_user_status")
    op.execute("DROP TABLE IF EXISTS shared.mai_proposals")
