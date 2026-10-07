"""Module Kho GĐ1 (Mua Hàng) — danh mục SKU tồn + phiếu nhập/xuất/điều chỉnh.

Thay hệ "log nhập tay" cũ (ton_kho_items — GIỮ NGUYÊN, không đụng) bằng quản tồn
theo MÃ SP (SKU) cho phần HÀNG TIÊU CHUẨN (đệm/gối/vải/phụ kiện).

Adds 2 tables under schema muahang:
    kho_sp        — danh mục SKU tồn (ma_sp UNIQUE)
    kho_movement  — phiếu nhập/xuất/điều chỉnh (tồn = Σ theo loai, tính bằng SQL)

Tồn KHÔNG lưu cột: ton(ma_sp) = SUM(CASE loai WHEN 'nhap' THEN so_luong
WHEN 'xuat' THEN -so_luong ELSE so_luong END). reserved=0 (GĐ1).

Revision ID: 0043_kho_module
Revises: 0042_qc_module
Create Date: 2026-08-24
"""
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0043_kho_module"
down_revision: Union[str, None] = "0042_qc_module"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── kho_sp — danh mục SKU tồn ─────────────────────────────────────────────
    op.create_table(
        "kho_sp",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ma_sp", sa.String(length=64), nullable=False),
        sa.Column("ten_sp", sa.String(length=255), nullable=False),
        sa.Column("nhom", sa.String(length=64), nullable=True),
        sa.Column("thuoc_tinh", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "dvt", sa.String(length=32), nullable=True, server_default=sa.text("'cái'")
        ),
        sa.Column("ncc_id", sa.String(length=64), nullable=True),
        sa.Column("ncc_name", sa.String(length=255), nullable=True),
        sa.Column(
            "don_gia_nhap", sa.Numeric(15, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ma_sp", name="uq_kho_sp_ma_sp"),
        schema="muahang",
    )
    op.create_index("ix_kho_sp_nhom", "kho_sp", ["nhom"], schema="muahang")
    op.create_index("ix_kho_sp_active", "kho_sp", ["active"], schema="muahang")

    # ── kho_movement — phiếu nhập/xuất/điều chỉnh ─────────────────────────────
    op.create_table(
        "kho_movement",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ma_sp", sa.String(length=64), nullable=False),
        sa.Column("loai", sa.String(length=16), nullable=False),
        sa.Column("so_luong", sa.Numeric(15, 2), nullable=False),
        sa.Column(
            "don_gia", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("nguon", sa.String(length=24), nullable=True),
        sa.Column("ref_type", sa.String(length=16), nullable=True),
        sa.Column("ref_id", sa.String(length=64), nullable=True),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("nguoi", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="muahang",
    )
    op.create_index("ix_kho_mv_ma_sp", "kho_movement", ["ma_sp"], schema="muahang")
    op.create_index("ix_kho_mv_loai", "kho_movement", ["loai"], schema="muahang")
    op.create_index(
        "ix_kho_mv_created_at", "kho_movement", ["created_at"], schema="muahang"
    )
    op.create_index(
        "ix_kho_mv_ref", "kho_movement", ["ref_type", "ref_id"], schema="muahang"
    )


def downgrade() -> None:
    op.drop_index("ix_kho_mv_ref", table_name="kho_movement", schema="muahang")
    op.drop_index("ix_kho_mv_created_at", table_name="kho_movement", schema="muahang")
    op.drop_index("ix_kho_mv_loai", table_name="kho_movement", schema="muahang")
    op.drop_index("ix_kho_mv_ma_sp", table_name="kho_movement", schema="muahang")
    op.drop_table("kho_movement", schema="muahang")

    op.drop_index("ix_kho_sp_active", table_name="kho_sp", schema="muahang")
    op.drop_index("ix_kho_sp_nhom", table_name="kho_sp", schema="muahang")
    op.drop_table("kho_sp", schema="muahang")
