"""Mai Policies — thêm scope/scope_value để hỗ trợ policy theo phòng ban / nhân viên.

Revision ID: 0027_mai_policy_scope
Revises: 0026_mai_policies
Create Date: 2026-05-23

Mở rộng `shared.mai_policies`:
- `scope`        : 'company' | 'department' | 'employee'    (default 'company')
- `scope_value`  : NULL khi company; tên phòng ban khi department;
                   username khi employee.

UNIQUE INDEX mới: (source, rule_type, scope, COALESCE(scope_value, ''))
→ cho phép cùng (source, rule_type) tồn tại nhiều scope khác nhau.

Idempotent: dùng IF EXISTS / IF NOT EXISTS + DO $$ ... EXCEPTION WHEN OTHERS
THEN NULL; END $$; — chạy lại migration nhiều lần không fail.

Backward compat: rows cũ sau ALTER tự động có scope='company', scope_value=NULL
→ logic check policy company-wide không đổi.

Seed bổ sung: `duyet_chi.max_amount` theo phòng ban (Marketing 10tr, Kế Toán 5tr,
HCNS 8tr, Sale Admin 5tr, Báo Giá 5tr, Mua Hàng 5tr).
"""
from alembic import op


revision = "0027_mai_policy_scope"
down_revision = "0026_mai_policies"
branch_labels = None
depends_on = None


# Seed defaults per-department cho duyet_chi.max_amount
# (scope, scope_value, source, rule_type, value, unit, note)
_DEPT_SEEDS = [
    ("department", "Marketing",  "duyet_chi", "max_amount", 10000000, "VND",
     "Duyệt chi Marketing ≤ 10tr"),
    ("department", "Kế Toán",    "duyet_chi", "max_amount", 5000000,  "VND",
     "Duyệt chi Kế Toán ≤ 5tr"),
    ("department", "HCNS",       "duyet_chi", "max_amount", 8000000,  "VND",
     "Duyệt chi HCNS ≤ 8tr"),
    ("department", "Sale Admin", "duyet_chi", "max_amount", 5000000,  "VND",
     "Duyệt chi Sale Admin ≤ 5tr"),
    ("department", "Báo Giá",    "duyet_chi", "max_amount", 5000000,  "VND",
     "Duyệt chi Báo Giá ≤ 5tr"),
    ("department", "Mua Hàng",   "duyet_chi", "max_amount", 5000000,  "VND",
     "Duyệt chi Mua Hàng ≤ 5tr"),
]


def upgrade():
    # ── 1) ADD COLUMN scope/scope_value (idempotent) ──────────────────
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE shared.mai_policies
                ADD COLUMN IF NOT EXISTS scope VARCHAR(32) NOT NULL DEFAULT 'company';
        EXCEPTION WHEN OTHERS THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE shared.mai_policies
                ADD COLUMN IF NOT EXISTS scope_value TEXT NULL;
        EXCEPTION WHEN OTHERS THEN NULL;
        END $$;
    """)

    # Rows cũ (nếu có) đã có default 'company' nhờ DEFAULT clause.
    # Đảm bảo không có NULL leak:
    op.execute("""
        UPDATE shared.mai_policies
           SET scope = 'company'
         WHERE scope IS NULL
    """)

    # ── 2) DROP unique index/constraint cũ (source, rule_type) ────────
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE shared.mai_policies
                DROP CONSTRAINT IF EXISTS ux_mai_policies_source_rule;
        EXCEPTION WHEN OTHERS THEN NULL;
        END $$;
    """)
    op.execute("DROP INDEX IF EXISTS shared.ux_mai_policies_source_rule")

    # ── 3) CREATE UNIQUE INDEX mới (source, rule_type, scope, COALESCE(scope_value, '')) ──
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_mai_policies_source_rule_scope
        ON shared.mai_policies
           (source, rule_type, scope, (COALESCE(scope_value, '')))
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mai_policies_scope
        ON shared.mai_policies (scope, scope_value)
    """)

    # ── 4) Seed thêm per-department (idempotent qua ON CONFLICT) ──────
    for scope, scope_val, src, rule, val, unit, note in _DEPT_SEEDS:
        sv_safe = scope_val.replace("'", "''")
        note_safe = note.replace("'", "''")
        op.execute(f"""
            INSERT INTO shared.mai_policies
                (source, rule_type, value, unit, note, enabled, scope, scope_value)
            VALUES
                ('{src}', '{rule}', {val}, '{unit}',
                 '{note_safe}', TRUE, '{scope}', '{sv_safe}')
            ON CONFLICT (source, rule_type, scope, (COALESCE(scope_value, '')))
            DO NOTHING
        """)


def downgrade():
    # Xoá index mới + restore index cũ
    op.execute("DROP INDEX IF EXISTS shared.ix_mai_policies_scope")
    op.execute("DROP INDEX IF EXISTS shared.ux_mai_policies_source_rule_scope")

    # Xoá các row có scope != 'company' để khỏi vi phạm unique cũ
    op.execute("""
        DELETE FROM shared.mai_policies
         WHERE scope IS DISTINCT FROM 'company'
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_mai_policies_source_rule
        ON shared.mai_policies (source, rule_type)
    """)

    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE shared.mai_policies DROP COLUMN IF EXISTS scope_value;
        EXCEPTION WHEN OTHERS THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE shared.mai_policies DROP COLUMN IF EXISTS scope;
        EXCEPTION WHEN OTHERS THEN NULL;
        END $$;
    """)
