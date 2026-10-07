"""Directive status v2 — mở rộng 5 status + tracking timestamps.

Revision ID: 0032_directive_status_v2
Revises: 0031_mai_insights
Create Date: 2026-05-26

Thay đổi:
  - Thêm 6 cột timestamp/text vào `shared.directives`:
      acknowledged_at, started_at, blocked_at, blocked_reason,
      last_activity_at (DEFAULT NOW()), completed_at
  - Migrate dữ liệu legacy:
      open    → assigned
      dropped → cancelled
  - Thêm index `ix_directives_last_activity` trên last_activity_at

Status mới (5 giá trị):
  assigned     — vừa giao, NV chưa start
  in_progress  — NV đang làm
  blocked      — NV pause (kèm blocked_reason)
  done         — NV hoàn thành
  cancelled    — CEO/from_user huỷ

Idempotent: dùng IF NOT EXISTS / IF EXISTS cho mọi DDL.
"""
from alembic import op


revision = "0032_directive_status_v2"
down_revision = "0031_mai_insights"
branch_labels = None
depends_on = None


def upgrade():
    # ── Add 6 columns (nullable, idempotent) ──────────────────────────────
    op.execute("""
        ALTER TABLE shared.directives
          ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ NULL
    """)
    op.execute("""
        ALTER TABLE shared.directives
          ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ NULL
    """)
    op.execute("""
        ALTER TABLE shared.directives
          ADD COLUMN IF NOT EXISTS blocked_at TIMESTAMPTZ NULL
    """)
    op.execute("""
        ALTER TABLE shared.directives
          ADD COLUMN IF NOT EXISTS blocked_reason TEXT NULL
    """)
    op.execute("""
        ALTER TABLE shared.directives
          ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ NULL DEFAULT NOW()
    """)
    op.execute("""
        ALTER TABLE shared.directives
          ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ NULL
    """)

    # ── Backfill last_activity_at cho row cũ (NULL) — dùng created_at ─────
    op.execute("""
        UPDATE shared.directives
           SET last_activity_at = COALESCE(last_activity_at, created_at, NOW())
         WHERE last_activity_at IS NULL
    """)

    # ── Migrate status legacy ──────────────────────────────────────────────
    op.execute("""
        UPDATE shared.directives
           SET status = 'assigned'
         WHERE status = 'open'
    """)
    op.execute("""
        UPDATE shared.directives
           SET status = 'cancelled'
         WHERE status = 'dropped'
    """)

    # ── Backfill completed_at cho task đã 'done' ──────────────────────────
    op.execute("""
        UPDATE shared.directives
           SET completed_at = COALESCE(completed_at, closed_at)
         WHERE status = 'done' AND completed_at IS NULL
    """)

    # ── Index last_activity_at ────────────────────────────────────────────
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_directives_last_activity
            ON shared.directives (last_activity_at DESC)
    """)


def downgrade():
    # Revert status mapping (best-effort — không khôi phục được phân biệt
    # in_progress/blocked vì legacy chỉ có open).
    op.execute("""
        UPDATE shared.directives
           SET status = 'open'
         WHERE status IN ('assigned', 'in_progress', 'blocked')
    """)
    op.execute("""
        UPDATE shared.directives
           SET status = 'dropped'
         WHERE status = 'cancelled'
    """)

    op.execute("DROP INDEX IF EXISTS shared.ix_directives_last_activity")

    op.execute("ALTER TABLE shared.directives DROP COLUMN IF EXISTS completed_at")
    op.execute("ALTER TABLE shared.directives DROP COLUMN IF EXISTS last_activity_at")
    op.execute("ALTER TABLE shared.directives DROP COLUMN IF EXISTS blocked_reason")
    op.execute("ALTER TABLE shared.directives DROP COLUMN IF EXISTS blocked_at")
    op.execute("ALTER TABLE shared.directives DROP COLUMN IF EXISTS started_at")
    op.execute("ALTER TABLE shared.directives DROP COLUMN IF EXISTS acknowledged_at")
