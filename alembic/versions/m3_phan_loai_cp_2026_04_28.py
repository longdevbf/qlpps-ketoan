"""Phân loại chi phí — thêm cột nhom_chi_phi (ban_hang/quan_ly/tai_chinh/khac).

Phục vụ Báo cáo P&L (Lãi Lỗ) chuẩn mực kế toán:
  - chi_phi_phat_sinh.nhom_chi_phi  → biến phí nhóm theo chức năng
  - chi_phi_co_dinh.nhom_chi_phi    → định phí nhóm theo chức năng
  - loai_chi_phi.nhom_default       → mặc định cho danh mục, để FE fill khi tạo CP

Quy ước phân nhóm tự động cho `loai_chi_phi.nhom_default`:
  - 'ads', 'marketing', 'vận chuyển', 'vc', 'khuyến mãi', 'shipping' → 'ban_hang'
  - 'lãi vay', 'phí ngân hàng', 'phí nh' → 'tai_chinh'
  - 'thuê', 'điện', 'nước', 'internet', 'vpp', 'vp', 'văn phòng' → 'quan_ly'
  - còn lại → 'khac'

Sau khi backfill `loai_chi_phi.nhom_default`, mọi row hiện có trong
`chi_phi_phat_sinh` và `chi_phi_co_dinh` cũng được backfill theo
`loai_chi_phi.ten` tương ứng.

Revision ID: m3pl_2026_04_28
Revises: 0007_chi_phi_bridges
Create Date: 2026-04-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m3pl_2026_04_28"
down_revision: Union[str, None] = "m1inv_data_2026_04_28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# CASE WHEN để classify theo `ten` (lower) — tái dùng cho 3 lần backfill
# Dùng LIKE '%token%' (case-insensitive sau LOWER) thay vì regex word-boundary
# để tránh edge cases escape khi gửi qua psycopg.
_CLASSIFY_CASE = """
    CASE
        WHEN LOWER(COALESCE({col}, '')) LIKE '%ads%'
          OR LOWER(COALESCE({col}, '')) LIKE '%marketing%'
          OR LOWER(COALESCE({col}, '')) LIKE '%mkt%'
          OR LOWER(COALESCE({col}, '')) LIKE '%quảng cáo%'
          OR LOWER(COALESCE({col}, '')) LIKE '%quang cao%'
          OR LOWER(COALESCE({col}, '')) LIKE '%vận chuyển%'
          OR LOWER(COALESCE({col}, '')) LIKE '%van chuyen%'
          OR LOWER(COALESCE({col}, '')) LIKE '%khuyến mãi%'
          OR LOWER(COALESCE({col}, '')) LIKE '%khuyen mai%'
          OR LOWER(COALESCE({col}, '')) LIKE '%shipping%'
            THEN 'ban_hang'
        WHEN LOWER(COALESCE({col}, '')) LIKE '%lãi vay%'
          OR LOWER(COALESCE({col}, '')) LIKE '%lai vay%'
          OR LOWER(COALESCE({col}, '')) LIKE '%phí ngân hàng%'
          OR LOWER(COALESCE({col}, '')) LIKE '%phi ngan hang%'
          OR LOWER(COALESCE({col}, '')) LIKE '%phí nh%'
          OR LOWER(COALESCE({col}, '')) LIKE '%phi nh%'
            THEN 'tai_chinh'
        WHEN LOWER(COALESCE({col}, '')) LIKE '%thuê%'
          OR LOWER(COALESCE({col}, '')) LIKE '%thue%'
          OR LOWER(COALESCE({col}, '')) LIKE '%điện%'
          OR LOWER(COALESCE({col}, '')) LIKE '%dien%'
          OR LOWER(COALESCE({col}, '')) LIKE '%nước%'
          OR LOWER(COALESCE({col}, '')) LIKE '%internet%'
          OR LOWER(COALESCE({col}, '')) LIKE '%vpp%'
          OR LOWER(COALESCE({col}, '')) LIKE '%văn phòng%'
          OR LOWER(COALESCE({col}, '')) LIKE '%van phong%'
            THEN 'quan_ly'
        ELSE 'khac'
    END
"""


def upgrade() -> None:
    # 1. loai_chi_phi.nhom_default (NULLABLE — chỉ là gợi ý, FE fallback 'khac')
    op.add_column(
        "loai_chi_phi",
        sa.Column("nhom_default", sa.String(20), nullable=True, server_default="khac"),
        schema="ketoan",
    )

    # 2. chi_phi_phat_sinh.nhom_chi_phi
    op.add_column(
        "chi_phi_phat_sinh",
        sa.Column(
            "nhom_chi_phi", sa.String(20),
            nullable=False, server_default="khac",
        ),
        schema="ketoan",
    )
    op.create_index(
        "ix_cpps_nhom",
        "chi_phi_phat_sinh", ["nhom_chi_phi"],
        schema="ketoan",
    )

    # 3. chi_phi_co_dinh.nhom_chi_phi
    op.add_column(
        "chi_phi_co_dinh",
        sa.Column(
            "nhom_chi_phi", sa.String(20),
            nullable=False, server_default="khac",
        ),
        schema="ketoan",
    )
    op.create_index(
        "ix_cpcd_nhom",
        "chi_phi_co_dinh", ["nhom_chi_phi"],
        schema="ketoan",
    )

    # ── Data backfill ──
    # 4. loai_chi_phi.nhom_default theo `ten`
    op.execute(
        f"""
        UPDATE ketoan.loai_chi_phi
        SET nhom_default = {_CLASSIFY_CASE.format(col='ten')}
        """
    )

    # 5. chi_phi_phat_sinh.nhom_chi_phi: ưu tiên loai_chi_phi.nhom_default,
    #    fallback classify trực tiếp từ chính loai_chi_phi (chuỗi)
    op.execute(
        """
        UPDATE ketoan.chi_phi_phat_sinh cp
        SET nhom_chi_phi = COALESCE(lcp.nhom_default, 'khac')
        FROM ketoan.loai_chi_phi lcp
        WHERE lcp.ten = cp.loai_chi_phi
        """
    )
    # cho rows không có FK match → classify từ string trực tiếp
    op.execute(
        f"""
        UPDATE ketoan.chi_phi_phat_sinh
        SET nhom_chi_phi = {_CLASSIFY_CASE.format(col='loai_chi_phi')}
        WHERE nhom_chi_phi = 'khac' AND loai_chi_phi IS NOT NULL
        """
    )

    # 6. chi_phi_co_dinh.nhom_chi_phi: tương tự
    op.execute(
        """
        UPDATE ketoan.chi_phi_co_dinh cp
        SET nhom_chi_phi = COALESCE(lcp.nhom_default, 'khac')
        FROM ketoan.loai_chi_phi lcp
        WHERE lcp.ten = cp.loai_chi_phi
        """
    )
    op.execute(
        f"""
        UPDATE ketoan.chi_phi_co_dinh
        SET nhom_chi_phi = {_CLASSIFY_CASE.format(col='loai_chi_phi')}
        WHERE nhom_chi_phi = 'khac' AND loai_chi_phi IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_cpcd_nhom", table_name="chi_phi_co_dinh", schema="ketoan")
    op.drop_column("chi_phi_co_dinh", "nhom_chi_phi", schema="ketoan")

    op.drop_index("ix_cpps_nhom", table_name="chi_phi_phat_sinh", schema="ketoan")
    op.drop_column("chi_phi_phat_sinh", "nhom_chi_phi", schema="ketoan")

    op.drop_column("loai_chi_phi", "nhom_default", schema="ketoan")
