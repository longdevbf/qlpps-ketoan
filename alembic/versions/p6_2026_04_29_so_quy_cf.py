"""so_quy: thêm cột phan_loai_cf cho báo cáo dòng tiền chuẩn

Migration backfill heuristic-based cho data hiện có:
- chi + lien_quan ILIKE %ncc% → 'tra_ncc'
- chi + lien_quan ILIKE %luong% / %payroll% → 'tra_luong'
- chi + ads keywords → 'nap_ads'
- thu + lien_quan ILIKE %vay% → 'vay_nh'
- thu + lien_quan ILIKE %kh%/%order% → 'thu_kh'
- chi + lai_vay/no_nh → 'tra_nh'
- chi + ccdc/tai_san → 'mua_ccdc'
- còn lại → NULL (kế toán phải chọn lại tay)
"""
from alembic import op
import sqlalchemy as sa


revision: str = "p6_2026_04_29_so_quy_cf"
down_revision = "p5c_2026_04_29"
branch_labels = None
depends_on = None


def upgrade():
    # Cột enum-as-string. Nullable trong giai đoạn migrate (sẽ fill dần qua UI).
    op.add_column(
        "so_quy",
        sa.Column("phan_loai_cf", sa.String(length=32), nullable=True),
        schema="ketoan",
    )
    op.create_index(
        "ix_so_quy_phan_loai_cf",
        "so_quy",
        ["phan_loai_cf"],
        schema="ketoan",
    )

    # Backfill từ heuristic (best-effort)
    op.execute("""
        UPDATE ketoan.so_quy SET phan_loai_cf = 'tra_ncc'
         WHERE loai='chi' AND phan_loai_cf IS NULL
           AND (lien_quan ILIKE '%ncc%' OR lien_quan ILIKE '%mua_hang%' OR lien_quan ILIKE '%phai_tra%');

        UPDATE ketoan.so_quy SET phan_loai_cf = 'tra_luong'
         WHERE loai='chi' AND phan_loai_cf IS NULL
           AND (lien_quan ILIKE '%luong%' OR lien_quan ILIKE '%payroll%' OR lien_quan ILIKE '%hcns%');

        UPDATE ketoan.so_quy SET phan_loai_cf = 'nap_ads'
         WHERE loai='chi' AND phan_loai_cf IS NULL
           AND (lien_quan ILIKE '%ads%' OR lien_quan ILIKE '%marketing%' OR lien_quan ILIKE '%mkt%'
                OR ghi_chu ILIKE '%facebook%' OR ghi_chu ILIKE '%google%' OR ghi_chu ILIKE '%ads%');

        UPDATE ketoan.so_quy SET phan_loai_cf = 'mua_ccdc'
         WHERE loai='chi' AND phan_loai_cf IS NULL
           AND (lien_quan ILIKE '%ccdc%' OR lien_quan ILIKE '%tai_san%' OR lien_quan ILIKE '%tscd%');

        UPDATE ketoan.so_quy SET phan_loai_cf = 'tra_nh'
         WHERE loai='chi' AND phan_loai_cf IS NULL
           AND (lien_quan ILIKE '%lai_vay%' OR lien_quan ILIKE '%no_nh%' OR lien_quan ILIKE '%tra_lai%');

        UPDATE ketoan.so_quy SET phan_loai_cf = 'vay_nh'
         WHERE loai='thu' AND phan_loai_cf IS NULL
           AND (lien_quan ILIKE '%vay%' OR lien_quan ILIKE '%loan%');

        UPDATE ketoan.so_quy SET phan_loai_cf = 'thu_kh'
         WHERE loai='thu' AND phan_loai_cf IS NULL
           AND (lien_quan ILIKE '%kh%' OR lien_quan ILIKE '%order%' OR lien_quan ILIKE '%don_hang%'
                OR lien_quan ILIKE '%doanh_thu%' OR lien_quan ILIKE '%phai_thu%');
    """)


def downgrade():
    op.drop_index("ix_so_quy_phan_loai_cf", table_name="so_quy", schema="ketoan")
    op.drop_column("so_quy", "phan_loai_cf", schema="ketoan")
