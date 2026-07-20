"""baseline schema ketoan (doanh_thu, chi_phi_phat_sinh, chi_phi_co_dinh,
cong_no, so_quy, loai_chi_phi, tai_khoan_nh)

Revision ID: 0001_baseline_ketoan
Revises:
Create Date: 2026-04-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_baseline_ketoan"
down_revision: Union[str, None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ketoan")

    # ----------------- loai_chi_phi -----------------
    op.create_table(
        "loai_chi_phi",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ten", sa.String(255), nullable=False, unique=True),
        sa.Column("mo_ta", sa.Text()),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        schema="ketoan",
    )

    # ----------------- tai_khoan_nh -----------------
    op.create_table(
        "tai_khoan_nh",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ten_tk", sa.String(255), nullable=False),
        sa.Column("loai", sa.String(32), server_default="ngan_hang", nullable=False),
        sa.Column("ten_nh", sa.String(128)),
        sa.Column("so_tk", sa.String(64), unique=True),
        sa.Column("chu_tk", sa.String(255)),
        sa.Column("chi_nhanh", sa.String(255)),
        sa.Column("so_du_dau", sa.Numeric(15, 2), server_default="0", nullable=False),
        sa.Column("mo_ta", sa.Text()),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="ketoan",
    )

    # ----------------- doanh_thu -----------------
    op.create_table(
        "doanh_thu",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ngay", sa.Date(), nullable=False),
        sa.Column("loai", sa.String(64)),
        sa.Column("so_tien", sa.Numeric(15, 2), server_default="0", nullable=False),
        sa.Column("nguon", sa.String(32)),
        sa.Column("nv_kinh_doanh", sa.String(128)),
        sa.Column("ma_don", sa.String(64)),
        sa.Column("ngan_hang", sa.String(128)),
        sa.Column("loai_thanh_toan", sa.String(32)),
        sa.Column("mo_ta", sa.Text()),
        sa.Column("ghi_chu", sa.Text()),
        sa.Column("created_by", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="ketoan",
    )
    op.create_index("ix_doanh_thu_ngay", "doanh_thu", ["ngay"], schema="ketoan")
    op.create_index("ix_doanh_thu_loai", "doanh_thu", ["loai"], schema="ketoan")
    op.create_index("ix_doanh_thu_nv", "doanh_thu", ["nv_kinh_doanh"], schema="ketoan")

    # ----------------- chi_phi_phat_sinh -----------------
    op.create_table(
        "chi_phi_phat_sinh",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ngay", sa.Date(), nullable=False),
        sa.Column("so_tien", sa.Numeric(15, 2), server_default="0", nullable=False),
        sa.Column("loai_chi_phi", sa.String(128)),
        sa.Column("quy", sa.String(64)),
        sa.Column("phong_ban", sa.String(128)),
        sa.Column("nguoi_chi", sa.String(128)),
        sa.Column("don_vi_vc", sa.String(128)),
        sa.Column("ma_don", sa.String(64)),
        sa.Column("ngan_hang", sa.String(128)),
        sa.Column("hoa_don_url", sa.String(512)),
        sa.Column("mo_ta", sa.Text()),
        sa.Column("ghi_chu", sa.Text()),
        sa.Column("created_by", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="ketoan",
    )
    op.create_index("ix_cpps_ngay", "chi_phi_phat_sinh", ["ngay"], schema="ketoan")
    op.create_index("ix_cpps_loai", "chi_phi_phat_sinh", ["loai_chi_phi"], schema="ketoan")

    # ----------------- chi_phi_co_dinh -----------------
    op.create_table(
        "chi_phi_co_dinh",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thang_bat_dau", sa.Date(), nullable=False),
        sa.Column("so_tien_thang", sa.Numeric(15, 2), server_default="0", nullable=False),
        sa.Column("loai_chi_phi", sa.String(128)),
        sa.Column("mo_ta", sa.Text()),
        sa.Column("ghi_chu", sa.Text()),
        sa.Column("lap_lai", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="ketoan",
    )
    op.create_index("ix_cpcd_thang", "chi_phi_co_dinh", ["thang_bat_dau"], schema="ketoan")
    op.create_index("ix_cpcd_loai", "chi_phi_co_dinh", ["loai_chi_phi"], schema="ketoan")

    # ----------------- cong_no -----------------
    op.create_table(
        "cong_no",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("ngay", sa.Date(), nullable=False),
        sa.Column("doi_tac", sa.String(255), nullable=False),
        sa.Column("so_tien", sa.Numeric(15, 2), server_default="0", nullable=False),
        sa.Column("da_tra", sa.Numeric(15, 2), server_default="0", nullable=False),
        sa.Column(
            "con_lai", sa.Numeric(15, 2),
            sa.Computed("so_tien - da_tra", persisted=True),
        ),
        sa.Column("loai", sa.String(32), nullable=False),
        sa.Column("loai_chi_tiet", sa.String(64)),
        sa.Column("ma_don", sa.String(64)),
        sa.Column("ref_id", sa.String(128)),
        sa.Column("ref_source", sa.String(32)),
        sa.Column("han_thanh_toan", sa.String(64)),
        sa.Column("trang_thai", sa.String(32), server_default="chua_tra", nullable=False),
        sa.Column("ngay_tra", sa.Date()),
        sa.Column("ghi_chu", sa.Text()),
        sa.Column("created_by", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="ketoan",
    )
    op.create_index("ix_cn_ngay", "cong_no", ["ngay"], schema="ketoan")
    op.create_index("ix_cn_loai", "cong_no", ["loai"], schema="ketoan")
    op.create_index("ix_cn_trang_thai", "cong_no", ["trang_thai"], schema="ketoan")
    # Partial unique idx — dedup auto_import
    op.execute(
        "CREATE UNIQUE INDEX uq_cn_ref_id ON ketoan.cong_no (ref_id) WHERE ref_id IS NOT NULL"
    )

    # ----------------- so_quy -----------------
    op.create_table(
        "so_quy",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ngay", sa.Date(), nullable=False),
        sa.Column("loai", sa.String(16), nullable=False),
        sa.Column("so_tien", sa.Numeric(15, 2), server_default="0", nullable=False),
        sa.Column("tai_khoan", sa.String(128)),
        sa.Column("noi_dung", sa.Text()),
        sa.Column("lien_quan", sa.String(128)),
        sa.Column("ref_id", sa.String(128)),
        sa.Column("mo_ta", sa.Text()),
        sa.Column("ghi_chu", sa.Text()),
        sa.Column("created_by", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="ketoan",
    )
    op.create_index("ix_sq_ngay", "so_quy", ["ngay"], schema="ketoan")
    op.create_index("ix_sq_loai", "so_quy", ["loai"], schema="ketoan")
    op.create_index("ix_sq_tk", "so_quy", ["tai_khoan"], schema="ketoan")


def downgrade() -> None:
    op.drop_table("so_quy", schema="ketoan")
    op.execute("DROP INDEX IF EXISTS ketoan.uq_cn_ref_id")
    op.drop_table("cong_no", schema="ketoan")
    op.drop_table("chi_phi_co_dinh", schema="ketoan")
    op.drop_table("chi_phi_phat_sinh", schema="ketoan")
    op.drop_table("doanh_thu", schema="ketoan")
    op.drop_table("tai_khoan_nh", schema="ketoan")
    op.drop_table("loai_chi_phi", schema="ketoan")
