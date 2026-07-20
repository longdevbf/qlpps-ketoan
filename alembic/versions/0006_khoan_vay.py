"""khoan_vay + khoan_vay_lai_suat + khoan_vay_giao_dich

Module Quản Lý Vốn Vay:
  - khoan_vay (master): mã/nguồn/số tiền/kỳ hạn/phương thức trả/status
  - khoan_vay_lai_suat (history): lãi suất % năm theo từng giai đoạn
  - khoan_vay_giao_dich (journal): giải ngân + trả gốc + trả lãi, link sang so_quy + chi_phi

Revision ID: 0006_khoan_vay
Revises: 0005_add_doanh_thu_chung_tu
Create Date: 2026-04-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_khoan_vay"
down_revision: Union[str, None] = "0005_add_doanh_thu_chung_tu"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── khoan_vay ─────────────────────────────────────────────────────────
    op.create_table(
        "khoan_vay",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ma_khoan", sa.String(64), nullable=False),
        sa.Column("nguon_vay", sa.String(128), nullable=False),
        sa.Column("loai_vay", sa.String(32), nullable=False, server_default="tin_chap"),
        sa.Column("so_tien_vay", sa.Numeric(15, 2), nullable=False),
        sa.Column("ngay_vay", sa.Date(), nullable=False),
        sa.Column("ky_han_thang", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("ngay_dao_han", sa.Date(), nullable=True),
        sa.Column(
            "phuong_thuc_tra", sa.String(32),
            nullable=False, server_default="tu_do",
        ),
        sa.Column("tai_san_the_chap", sa.Text(), nullable=True),
        sa.Column("tai_khoan_giai_ngan", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="dang_vay"),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("ma_khoan", name="uq_khoan_vay_ma"),
        schema="ketoan",
    )
    op.create_index("ix_kv_status", "khoan_vay", ["status"], schema="ketoan")
    op.create_index("ix_kv_nguon", "khoan_vay", ["nguon_vay"], schema="ketoan")

    # ─── khoan_vay_lai_suat (lịch sử % năm) ────────────────────────────────
    op.create_table(
        "khoan_vay_lai_suat",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("khoan_vay_id", sa.Integer(), nullable=False),
        sa.Column("tu_ngay", sa.Date(), nullable=False),
        sa.Column("lai_suat_nam", sa.Numeric(6, 3), nullable=False),  # vd 8.500 = 8.5%
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["khoan_vay_id"], ["ketoan.khoan_vay.id"],
            name="fk_kvls_khoan_vay", ondelete="CASCADE",
        ),
        schema="ketoan",
    )
    op.create_index(
        "ix_kvls_khoan_tu_ngay", "khoan_vay_lai_suat",
        ["khoan_vay_id", "tu_ngay"], schema="ketoan",
    )

    # ─── khoan_vay_giao_dich (nhật ký + link so_quy/chi_phi) ───────────────
    op.create_table(
        "khoan_vay_giao_dich",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("khoan_vay_id", sa.Integer(), nullable=False),
        # 'giai_ngan' | 'tra_goc' | 'tra_lai' | 'tra_goc_lai' | 'phat'
        sa.Column("loai", sa.String(32), nullable=False),
        sa.Column("ngay", sa.Date(), nullable=False),
        sa.Column("so_tien", sa.Numeric(15, 2), nullable=False),
        sa.Column("so_tien_goc", sa.Numeric(15, 2), nullable=True),  # khi loai='tra_goc_lai' tách goc/lai
        sa.Column("so_tien_lai", sa.Numeric(15, 2), nullable=True),
        sa.Column("ref_so_quy_id", sa.Integer(), nullable=True),
        sa.Column("ref_chi_phi_id", sa.Integer(), nullable=True),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["khoan_vay_id"], ["ketoan.khoan_vay.id"],
            name="fk_kvgd_khoan_vay", ondelete="CASCADE",
        ),
        schema="ketoan",
    )
    op.create_index(
        "ix_kvgd_khoan_loai", "khoan_vay_giao_dich",
        ["khoan_vay_id", "loai"], schema="ketoan",
    )
    op.create_index(
        "ix_kvgd_ngay", "khoan_vay_giao_dich", ["ngay"], schema="ketoan",
    )

    # Seed loại chi phí "Lãi vay" nếu chưa có (cần cho trả lãi)
    op.execute("""
        INSERT INTO ketoan.loai_chi_phi (ten, mo_ta, active)
        SELECT 'Lãi vay', 'Chi phí lãi vay ngân hàng (auto từ module Vốn Vay)', true
        WHERE NOT EXISTS (
            SELECT 1 FROM ketoan.loai_chi_phi WHERE ten = 'Lãi vay'
        );
    """)


def downgrade() -> None:
    op.drop_index("ix_kvgd_ngay", table_name="khoan_vay_giao_dich", schema="ketoan")
    op.drop_index("ix_kvgd_khoan_loai", table_name="khoan_vay_giao_dich", schema="ketoan")
    op.drop_table("khoan_vay_giao_dich", schema="ketoan")

    op.drop_index("ix_kvls_khoan_tu_ngay", table_name="khoan_vay_lai_suat", schema="ketoan")
    op.drop_table("khoan_vay_lai_suat", schema="ketoan")

    op.drop_index("ix_kv_nguon", table_name="khoan_vay", schema="ketoan")
    op.drop_index("ix_kv_status", table_name="khoan_vay", schema="ketoan")
    op.drop_table("khoan_vay", schema="ketoan")
