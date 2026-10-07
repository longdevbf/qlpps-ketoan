"""Mai auto-decisions log — 1 row per item Mai xét trong inbox_review.

Revision ID: 0034_mai_auto_decisions
Revises: 0033_nhanh_username, 0032_directive_status_v2
Create Date: 2026-05-28

Tách riêng với `mai_interaction` (chat) — bảng này log mọi quyết định
auto của Mai trên các source approval: duyet_chi, xin_nghi, baogia_quote,
muahang_po, marketing_km, denghitt, lenh_di_do, shared_approval.

CEO mở dashboard /mai/auto-decisions filter theo source → thấy đầy đủ
phiếu nào Mai đã duyệt / escalate / skip + lý do + applicable_rules.
"""
from alembic import op


revision = "0034_mai_auto_decisions"
down_revision = "0033_nhanh_username"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")

    op.execute("""
        CREATE TABLE IF NOT EXISTS shared.mai_auto_decisions (
            id              BIGSERIAL PRIMARY KEY,
            source          VARCHAR(32) NOT NULL,   -- duyet_chi|xin_nghi|baogia_quote|...
            ref_id          VARCHAR(64) NOT NULL,
            ref_label       TEXT NULL,              -- title/tieu_de cho dễ đọc
            decision        VARCHAR(16) NOT NULL,   -- auto_approve|escalate|skip
            executed        BOOLEAN NOT NULL DEFAULT FALSE,
            exec_error      TEXT NULL,
            amount          NUMERIC(15,2) NULL,
            currency        VARCHAR(8) NULL,
            requested_by_username VARCHAR(64) NULL,
            requested_by_name     VARCHAR(255) NULL,
            current_step    VARCHAR(32) NULL,       -- approval_level lúc Mai xét
            reason          TEXT NULL,
            applicable_rules JSONB NULL,
            gap             NUMERIC(15,2) NULL,     -- vượt hạn mức bao nhiêu (escalate case)
            age_hours       NUMERIC(8,2) NULL,
            dry_run         BOOLEAN NOT NULL DEFAULT FALSE,
            review_run_id   VARCHAR(32) NULL,       -- group các decision cùng 1 lần run
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_dec_source_time
                  ON shared.mai_auto_decisions (source, created_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_dec_decision_time
                  ON shared.mai_auto_decisions (decision, created_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_dec_user
                  ON shared.mai_auto_decisions (requested_by_username, created_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_dec_created
                  ON shared.mai_auto_decisions (created_at DESC)""")
    # UNIQUE để mỗi lần run không double-log cùng item — chỉ guard live (dry_run=FALSE)
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_mai_dec_run_ref
                  ON shared.mai_auto_decisions (review_run_id, source, ref_id)
                  WHERE review_run_id IS NOT NULL""")


def downgrade():
    op.execute("DROP INDEX IF EXISTS shared.uq_mai_dec_run_ref")
    op.execute("DROP INDEX IF EXISTS shared.ix_mai_dec_created")
    op.execute("DROP INDEX IF EXISTS shared.ix_mai_dec_user")
    op.execute("DROP INDEX IF EXISTS shared.ix_mai_dec_decision_time")
    op.execute("DROP INDEX IF EXISTS shared.ix_mai_dec_source_time")
    op.execute("DROP TABLE IF EXISTS shared.mai_auto_decisions")
