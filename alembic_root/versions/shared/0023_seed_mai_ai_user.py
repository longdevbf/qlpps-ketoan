"""seed user 'mai_ai' — Mai xuất hiện như 1 nhân viên trong chat picker

Revision ID: 0023_seed_mai_ai_user
Revises: 0022_ai_chat_message
Create Date: 2026-05-23

Idempotent: dùng INSERT ON CONFLICT DO NOTHING — chạy lại không lỗi.
"""
from alembic import op


revision = "0023_seed_mai_ai_user"
down_revision = "0022_ai_chat_message"
branch_labels = None
depends_on = None


# Password hash dummy (bcrypt of "ai-assistant-no-login") — Mai không cần đăng nhập
# nhưng schema yêu cầu password_hash NOT NULL.
DUMMY_PASSWORD_HASH = "$2b$12$AbCdEfGhIjKlMnOpQrStUuV1234567890abcdEFGH.IJKLMNOPQ"


def upgrade():
    # 1) shared.users — Mai như 1 user thực, role 'ai_assistant'
    op.execute(f"""
        INSERT INTO shared.users
            (username, email, password_hash, full_name, role, apps, active, is_on_duty, created_at, updated_at)
        VALUES
            ('mai_ai', 'mai-ai@qlpps.internal', '{DUMMY_PASSWORD_HASH}', 'Mai - Trợ Lý',
             'ai_assistant',
             ARRAY['baogia','marketing','muahang','hcns','ketoan','saleadmin','ceo'],
             TRUE, TRUE, NOW(), NOW())
        ON CONFLICT (username) DO UPDATE SET
            full_name = EXCLUDED.full_name,
            role = EXCLUDED.role,
            apps = EXCLUDED.apps,
            active = TRUE,
            updated_at = NOW();
    """)

    # 2) hcns.employees — record để picker hiển thị + chat avatar
    op.execute(f"""
        INSERT INTO hcns.employees
            (ma_nv, ho_ten, phong_ban, chuc_vu, trang_thai,
             username, password_hash, role, luong_co_ban, so_npt, created_at, updated_at)
        VALUES
            ('AI_MAI', 'Mai - Trợ Lý', 'Trợ lý AI', 'AI Assistant', 'Đang làm',
             'mai_ai', '{DUMMY_PASSWORD_HASH}', 'ai_assistant', 0, 0, NOW(), NOW())
        ON CONFLICT (ma_nv) DO UPDATE SET
            ho_ten = EXCLUDED.ho_ten,
            phong_ban = EXCLUDED.phong_ban,
            chuc_vu = EXCLUDED.chuc_vu,
            trang_thai = 'Đang làm',
            role = EXCLUDED.role,
            updated_at = NOW();
    """)


def downgrade():
    op.execute("DELETE FROM hcns.employees WHERE ma_nv = 'AI_MAI'")
    op.execute("DELETE FROM shared.users WHERE username = 'mai_ai'")
