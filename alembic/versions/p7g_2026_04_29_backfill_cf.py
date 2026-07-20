"""Sprint 7G — backfill `phan_loai_cf` cho data so_quy cũ.

Migration P6 (`p6_2026_04_29_so_quy_cf`) đã thêm cột `phan_loai_cf` và backfill
sơ bộ theo `lien_quan`. P7G phủ sót: dùng thêm pattern `noi_dung` / `ref_vc`
và đảm bảo KHÔNG còn NULL nào (default `'khac'`).

Quy ước:
- Vay NH:    thu + lien_quan LIKE 'vay_%'             -> 'vay_nh'
- Trả NH:    chi + lien_quan LIKE 'vay_%'             -> 'tra_nh'
- Thu KH:    thu + (lien_quan='vanchuyen' OR ref_vc IS NOT NULL) -> 'thu_kh'
- Mua TSCĐ:  chi + (lien_quan='tscd' OR noi_dung chứa tscđ/tscd/ccdc) -> 'mua_ccdc'
- Trả lương: chi + noi_dung chứa lương/luong/payroll  -> 'tra_luong'
- Nạp Ads:   chi + noi_dung chứa ads/marketing/fb/facebook/google -> 'nap_ads'
- VCSH:      lien_quan='vcsh'                          -> 'khac'
- Còn lại:                                              -> 'khac'
"""
from alembic import op


revision: str = "p7g_2026_04_29_backfill_cf"
down_revision = "q1_2026_04_29"
branch_labels = None
depends_on = None


def upgrade():
    # Vay NH (thu)
    op.execute("""
        UPDATE ketoan.so_quy SET phan_loai_cf='vay_nh'
         WHERE phan_loai_cf IS NULL AND loai='thu' AND lien_quan LIKE 'vay_%';
    """)

    # Trả NH (chi)
    op.execute("""
        UPDATE ketoan.so_quy SET phan_loai_cf='tra_nh'
         WHERE phan_loai_cf IS NULL AND loai='chi' AND lien_quan LIKE 'vay_%';
    """)

    # Vận chuyển COD -> thu KH
    op.execute("""
        UPDATE ketoan.so_quy SET phan_loai_cf='thu_kh'
         WHERE phan_loai_cf IS NULL AND loai='thu'
           AND (lien_quan='vanchuyen' OR ref_vc IS NOT NULL);
    """)

    # Mua TSCĐ / CCDC
    op.execute("""
        UPDATE ketoan.so_quy SET phan_loai_cf='mua_ccdc'
         WHERE phan_loai_cf IS NULL AND loai='chi'
           AND (lien_quan='tscd'
                OR LOWER(noi_dung) LIKE '%tscđ%'
                OR LOWER(noi_dung) LIKE '%tscd%'
                OR LOWER(noi_dung) LIKE '%ccdc%');
    """)

    # Trả lương
    op.execute("""
        UPDATE ketoan.so_quy SET phan_loai_cf='tra_luong'
         WHERE phan_loai_cf IS NULL AND loai='chi'
           AND (LOWER(noi_dung) LIKE '%lương%'
                OR LOWER(noi_dung) LIKE '%luong%'
                OR LOWER(noi_dung) LIKE '%payroll%');
    """)

    # Nạp Ads
    op.execute("""
        UPDATE ketoan.so_quy SET phan_loai_cf='nap_ads'
         WHERE phan_loai_cf IS NULL AND loai='chi'
           AND (LOWER(noi_dung) LIKE '%ads%'
                OR LOWER(noi_dung) LIKE '%marketing%'
                OR LOWER(noi_dung) LIKE '%fb%'
                OR LOWER(noi_dung) LIKE '%facebook%'
                OR LOWER(noi_dung) LIKE '%google%');
    """)

    # VCSH -> khac
    op.execute("""
        UPDATE ketoan.so_quy SET phan_loai_cf='khac'
         WHERE phan_loai_cf IS NULL AND lien_quan='vcsh';
    """)

    # Default: phần còn lại
    op.execute("""
        UPDATE ketoan.so_quy SET phan_loai_cf='khac'
         WHERE phan_loai_cf IS NULL;
    """)


def downgrade():
    # Backfill thuần data; không có schema change để đảo. Best-effort:
    # đặt lại NULL các rows được P7G gán 'khac' không phải VCSH (không xác định
    # được chính xác nên để no-op an toàn).
    pass
