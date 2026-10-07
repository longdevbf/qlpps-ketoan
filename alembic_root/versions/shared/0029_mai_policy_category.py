"""Mai Policies — thêm rule_category (loại chi cụ thể) + seed defaults CEO mới.

Revision ID: 0029_mai_policy_category
Revises: 0028_mai_proposals
Create Date: 2026-05-23

Mở rộng `shared.mai_policies`:
- `rule_category` : VARCHAR(64) NULL — loại chi cụ thể trong cùng 1 phòng ban.
  Ví dụ: 'cong_tac', 'ccdc', 'ads', 'van_tu', 'trang_thiet_bi', 'tam_ung',
  'default'. NULL khi rule áp dụng cho cả phòng (không phân loại).

UNIQUE INDEX mới: (source, rule_type, scope, COALESCE(scope_value,''),
                   COALESCE(rule_category,''))
→ Cho phép cùng (source, rule_type, department) có nhiều rule khác category.
  VD: Marketing có max_amount cho 'ads' = 60tr và 'van_tu' = 1tr.

Idempotent: IF NOT EXISTS / DO $$ ... EXCEPTION — chạy lại không fail.

Seed defaults (CEO chốt 2026-05-23):
  Duyệt chi (source='duyet_chi'):
    Báo Giá / cong_tac        → max=1tr, require_chung_tu=1
    HCNS / ccdc               → max=2tr, require_chung_tu=1
    Marketing / ads           → max=60tr, require_chung_tu=0
    Marketing / van_tu        → max=1tr, require_chung_tu=1
    Marketing / ccdc          → max=1tr, require_chung_tu=1
    Mua Hàng / trang_thiet_bi → max=1tr, require_chung_tu=1
    Sale Admin / tam_ung      → max=3tr, require_chung_tu=1
    Kế Toán / default         → max=2tr, require_chung_tu=1
  Đề nghị thanh toán (source='denghitt'):
    Sale Admin: require_chung_tu=1 (rule_category=NULL)
    Sale Admin: max_ship_pct_of_order=3% (rule_category=NULL)
"""
from alembic import op


revision = "0029_mai_policy_category"
down_revision = "0028_mai_proposals"
branch_labels = None
depends_on = None


# Seed defaults cho duyet_chi theo (phòng, rule_category)
# (department, rule_category, max_amount, require_chung_tu, note_max, note_ct)
_DUYET_CHI_SEEDS = [
    ("Báo Giá",   "cong_tac",       1_000_000, 1,
     "Báo Giá chi đi công tác ≤ 1tr",
     "Báo Giá công tác: yêu cầu chứng từ"),
    ("HCNS",      "ccdc",           2_000_000, 1,
     "HCNS mua CCDC ≤ 2tr",
     "HCNS CCDC: yêu cầu chứng từ"),
    ("Marketing", "ads",           60_000_000, 0,
     "Marketing chi Ads ≤ 60tr",
     "Marketing Ads: không bắt buộc chứng từ giấy"),
    ("Marketing", "van_tu",         1_000_000, 1,
     "Marketing mua văn tự ≤ 1tr",
     "Marketing văn tự: yêu cầu chứng từ"),
    ("Marketing", "ccdc",           1_000_000, 1,
     "Marketing mua CCDC ≤ 1tr",
     "Marketing CCDC: yêu cầu chứng từ"),
    ("Mua Hàng",  "trang_thiet_bi", 1_000_000, 1,
     "Mua Hàng mua trang thiết bị ≤ 1tr",
     "Mua Hàng TTB: yêu cầu chứng từ"),
    ("Sale Admin","tam_ung",        3_000_000, 1,
     "Sale Admin tạm ứng ≤ 3tr",
     "Sale Admin tạm ứng: yêu cầu chứng từ"),
    ("Kế Toán",   "default",        2_000_000, 1,
     "Kế Toán chi mặc định ≤ 2tr",
     "Kế Toán default: yêu cầu chứng từ"),
]


# Seed defaults cho denghitt (rule_category = NULL — áp cho cả phòng)
# (department, rule_type, value, unit, note)
_DENGHITT_SEEDS = [
    ("Sale Admin", "require_chung_tu",         1, "bool",
     "Sale Admin bắt buộc có chứng từ đính kèm"),
    ("Sale Admin", "max_ship_pct_of_order",    3, "%",
     "Tiền ship không quá 3% tổng đơn"),
]


def _esc(s: str) -> str:
    return s.replace("'", "''")


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")

    # ── 1) ADD COLUMN rule_category (idempotent) ─────────────────────
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE shared.mai_policies
                ADD COLUMN IF NOT EXISTS rule_category VARCHAR(64) NULL;
        EXCEPTION WHEN OTHERS THEN NULL;
        END $$;
    """)

    # ── 2) DROP unique index cũ (không có rule_category) ─────────────
    op.execute("DROP INDEX IF EXISTS shared.ux_mai_policies_source_rule_scope")

    # ── 3) CREATE UNIQUE INDEX mới gồm rule_category ─────────────────
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_mai_policies_source_rule_scope_cat
        ON shared.mai_policies
           (source, rule_type, scope,
            (COALESCE(scope_value, '')),
            (COALESCE(rule_category, '')))
    """)

    # ── 4) Seed duyet_chi per (department, rule_category) ────────────
    for dept, cat, max_amt, req_ct, note_max, note_ct in _DUYET_CHI_SEEDS:
        dept_s = _esc(dept)
        cat_s = _esc(cat)
        note_max_s = _esc(note_max)
        note_ct_s = _esc(note_ct)

        # max_amount row
        op.execute(f"""
            INSERT INTO shared.mai_policies
                (source, rule_type, value, unit, note, enabled,
                 scope, scope_value, rule_category)
            VALUES
                ('duyet_chi', 'max_amount', {max_amt}, 'VND',
                 '{note_max_s}', TRUE,
                 'department', '{dept_s}', '{cat_s}')
            ON CONFLICT (source, rule_type, scope,
                         (COALESCE(scope_value, '')),
                         (COALESCE(rule_category, '')))
            DO NOTHING
        """)

        # require_chung_tu row
        op.execute(f"""
            INSERT INTO shared.mai_policies
                (source, rule_type, value, unit, note, enabled,
                 scope, scope_value, rule_category)
            VALUES
                ('duyet_chi', 'require_chung_tu', {req_ct}, 'bool',
                 '{note_ct_s}', TRUE,
                 'department', '{dept_s}', '{cat_s}')
            ON CONFLICT (source, rule_type, scope,
                         (COALESCE(scope_value, '')),
                         (COALESCE(rule_category, '')))
            DO NOTHING
        """)

    # ── 5) Seed denghitt rules mới (rule_category = NULL) ────────────
    for dept, rtype, val, unit, note in _DENGHITT_SEEDS:
        dept_s = _esc(dept)
        rtype_s = _esc(rtype)
        unit_s = _esc(unit)
        note_s = _esc(note)
        op.execute(f"""
            INSERT INTO shared.mai_policies
                (source, rule_type, value, unit, note, enabled,
                 scope, scope_value, rule_category)
            VALUES
                ('denghitt', '{rtype_s}', {val}, '{unit_s}',
                 '{note_s}', TRUE,
                 'department', '{dept_s}', NULL)
            ON CONFLICT (source, rule_type, scope,
                         (COALESCE(scope_value, '')),
                         (COALESCE(rule_category, '')))
            DO NOTHING
        """)


def downgrade():
    # Xoá rows seed mới (chỉ rows có rule_category NOT NULL hoặc denghitt mới)
    op.execute("""
        DELETE FROM shared.mai_policies
         WHERE rule_category IS NOT NULL
    """)
    op.execute("""
        DELETE FROM shared.mai_policies
         WHERE source = 'denghitt'
           AND rule_type IN ('require_chung_tu', 'max_ship_pct_of_order')
    """)

    # Xoá unique index mới
    op.execute("DROP INDEX IF EXISTS shared.ux_mai_policies_source_rule_scope_cat")

    # Restore unique index cũ (không có rule_category)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_mai_policies_source_rule_scope
        ON shared.mai_policies
           (source, rule_type, scope, (COALESCE(scope_value, '')))
    """)

    # Drop column rule_category
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE shared.mai_policies DROP COLUMN IF EXISTS rule_category;
        EXCEPTION WHEN OTHERS THEN NULL;
        END $$;
    """)
