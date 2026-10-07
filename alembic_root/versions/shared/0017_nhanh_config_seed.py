"""Seed nhanh.vn credentials placeholder vào shared.app_config.

3 row:
    ('nhanhvn', 'credentials') — app_id/secret_key/business_id/redirect_url
    ('nhanhvn', 'token')       — access_token/expires_at (sẽ set sau OAuth)
    ('nhanhvn', 'auto_push')   — switch on/off

Admin sẽ paste creds qua UI /admin/nhanh-config. Migration chỉ seed empty.
"""
from alembic import op
from sqlalchemy import text


revision = "0017_nhanh_config_seed"
down_revision = "0016_expense_requests"
branch_labels = None
depends_on = None


def upgrade():
    # Use TextClause với escaped bind params (`:false` được SQLA parse là param)
    # → dùng text với explicit no-binds, hoặc cast trong SQL không có dấu :
    conn = op.get_bind()
    conn.execute(text(
        "INSERT INTO shared.app_config (app, key, value) VALUES "
        "('nhanhvn', 'credentials', cast(:cred as jsonb)), "
        "('nhanhvn', 'token',       cast(:tok  as jsonb)), "
        "('nhanhvn', 'auto_push',   cast(:ap   as jsonb)) "
        "ON CONFLICT (app, key) DO NOTHING"
    ), {
        "cred": '{"app_id":"","secret_key":"","business_id":"","redirect_url":""}',
        "tok": "{}",
        "ap": '{"enabled":false}',
    })


def downgrade():
    op.execute(
        "DELETE FROM shared.app_config WHERE app = 'nhanhvn';"
    )
