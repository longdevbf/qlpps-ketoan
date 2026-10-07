"""Đề xuất chấm công lại — bảng shared.de_xuat_cham_cong.

Nhân viên gửi (ngày, giờ đến thực tế, giờ trên hệ thống, lý do, số tiền đề xuất `phi`).
Duyệt 2 cấp Quản lý → CEO; CEO quyết định có trừ Tối ưu KD không và trừ bao nhiêu
(`phi_tru`). Duyệt xong ghi đè giờ vào trong hcns.cham_cong.

Revision ID: 0048_de_xuat_cham_cong
Revises: 0047_ngay_le_dip
Create Date: 2026-10-05
"""
from typing import Union

from alembic import op


revision: str = "0048_de_xuat_cham_cong"
down_revision: Union[str, None] = "0047_ngay_le_dip"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IDEMPOTENT: an toàn khi chạy lại / khi bảng đã được tạo tay trên prod.
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")
    op.execute("""
        CREATE TABLE IF NOT EXISTS shared.de_xuat_cham_cong (
            id                SERIAL PRIMARY KEY,
            username          VARCHAR(64)  NOT NULL,
            ma_nv             VARCHAR(16)  NOT NULL,
            ho_ten            VARCHAR(128) NOT NULL,
            phong_ban         VARCHAR(128),
            app_name          VARCHAR(32)  NOT NULL,
            ngay              DATE         NOT NULL,
            gio_thuc_te       TIME         NOT NULL,
            gio_he_thong      TIME,
            gio_truoc_khi_sua TIME,
            ly_do             TEXT         NOT NULL,
            phi               NUMERIC(15,0) NOT NULL DEFAULT 0,
            phi_tru           NUMERIC(15,0),
            trang_thai        VARCHAR(16)  NOT NULL DEFAULT 'cho_quan_ly',
            tu_choi_boi       VARCHAR(16),
            quan_ly_duyet     VARCHAR(64),
            ho_ten_quan_ly    VARCHAR(128),
            quan_ly_luc       TIMESTAMPTZ,
            quan_ly_nhan_xet  TEXT,
            ceo_duyet         VARCHAR(64),
            ho_ten_ceo        VARCHAR(128),
            ceo_luc           TIMESTAMPTZ,
            ceo_nhan_xet      TEXT,
            created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_de_xuat_cham_cong_username ON shared.de_xuat_cham_cong (username)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_de_xuat_cham_cong_trang_thai ON shared.de_xuat_cham_cong (trang_thai)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_de_xuat_cham_cong_ma_nv_created "
        "ON shared.de_xuat_cham_cong (ma_nv, created_at)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_de_xuat_cham_cong_hieu_luc "
        "ON shared.de_xuat_cham_cong (username, ngay) WHERE trang_thai <> 'tu_choi'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS shared.de_xuat_cham_cong")
