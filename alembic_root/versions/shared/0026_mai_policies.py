"""create shared.mai_policies table — Policies / Hạn mức / Định mức cho Mai AI

Revision ID: 0026_mai_policies
Revises: 0025_mai_preferences
Create Date: 2026-05-23

CEO nhập các "policy" (hạn mức / định mức) để Mai dùng làm điều kiện
quyết định auto-approve hay escalate (chuyển CEO duyệt).

  source     : 'baogia_quote' | 'muahang_po' | 'marketing_km' | 'duyet_chi'
               | 'denghitt' | 'xin_nghi' | 'lenh_di_do' | 'muahang_ncc_new'
               | 'hcns_salary_increase' | ...
  rule_type  : 'max_amount' | 'max_discount_pct' | 'max_percent'
               | 'max_days' | 'max_km' | 'enabled' | ...
  value      : Numeric(15,2) — threshold hoặc 0/1 cho rule_type='enabled'
  unit       : 'VND' | '%' | 'ngày' | 'km' | 'bool' | ...
  enabled    : bool — bật/tắt rule
  note       : mô tả ngắn (Mai dùng để giải thích cho CEO khi escalate)

Idempotent: dùng IF NOT EXISTS — chạy lại không fail.
Seed defaults: INSERT ... ON CONFLICT DO NOTHING.
"""
from alembic import op


revision = "0026_mai_policies"
down_revision = "0025_mai_preferences"
branch_labels = None
depends_on = None


# Seed defaults: (source, rule_type, value, unit, note)
_SEEDS = [
    ("baogia_quote", "max_amount", 30000000, "VND", "Mai auto-duyệt BG ≤ 30tr"),
    ("muahang_po", "max_amount", 50000000, "VND", "Mai auto-duyệt PO ≤ 50tr"),
    ("muahang_po", "max_discount_pct", 10, "%", "PO có discount > 10% → escalate CEO"),
    ("marketing_km", "max_percent", 15, "%", "KM giảm > 15% → escalate"),
    ("duyet_chi", "max_amount", 5000000, "VND", "Duyệt chi ≤ 5tr"),
    ("denghitt", "max_amount", 20000000, "VND", "Đề nghị TT ≤ 20tr"),
    ("xin_nghi", "max_days", 2, "ngày", "Nghỉ ≤ 2 ngày Mai duyệt"),
    ("lenh_di_do", "max_km", 100, "km", "Lệnh đi ≤ 100km Mai duyệt"),
    ("muahang_ncc_new", "enabled", 1, "bool", "NCC mới có phone+ten → Mai duyệt"),
    ("hcns_salary_increase", "enabled", 0, "bool", "KHÔNG cho Mai auto duyệt tăng lương"),
]


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")

    op.execute("""
        CREATE TABLE IF NOT EXISTS shared.mai_policies (
            id           SERIAL PRIMARY KEY,
            source       TEXT          NOT NULL,
            rule_type    TEXT          NOT NULL,
            value        NUMERIC(15,2) NULL,
            unit         TEXT          NULL,
            enabled      BOOLEAN       NOT NULL DEFAULT TRUE,
            note         TEXT          NULL,
            updated_by   TEXT          NULL,
            updated_at   TIMESTAMPTZ   NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_mai_policies_source_rule
        ON shared.mai_policies (source, rule_type)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mai_policies_source
        ON shared.mai_policies (source)
    """)

    # Seed defaults (idempotent qua ON CONFLICT)
    for src, rule, val, unit, note in _SEEDS:
        op.execute(f"""
            INSERT INTO shared.mai_policies (source, rule_type, value, unit, note, enabled)
            VALUES ('{src}', '{rule}', {val}, '{unit}',
                    '{note.replace("'", "''")}', TRUE)
            ON CONFLICT (source, rule_type) DO NOTHING
        """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS shared.ix_mai_policies_source")
    op.execute("DROP INDEX IF EXISTS shared.ux_mai_policies_source_rule")
    op.execute("DROP TABLE IF EXISTS shared.mai_policies")
