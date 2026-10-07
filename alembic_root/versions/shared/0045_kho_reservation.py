"""Module Kho GĐ3 — Giữ chỗ (reservation) tồn kho (kho_reservation).

Luồng tự chứa giữ chỗ → xuất bán / huỷ, SKU-native. KHÔNG đụng pipeline PO bán
hàng hay đề xuất. Khi xuất bán → ghi vào muahang.kho_movement (GĐ1) với
nguon='ban', ref_type='kho_reservation'. kha_dung = ton − reserved.

Adds 1 table under schema muahang:
    kho_reservation    — phiếu giữ chỗ (trang_thai giu|da_xuat|huy, ...)

Revision ID: 0045_kho_reservation
Revises: 0044_kho_dexuat
Create Date: 2026-08-24
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0045_kho_reservation"
down_revision: Union[str, None] = "0044_kho_dexuat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── kho_reservation — phiếu giữ chỗ tồn kho ────────────────────────────────
    op.create_table(
        "kho_reservation",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ma_sp", sa.String(length=64), nullable=False),
        sa.Column("ten_sp", sa.String(length=255), nullable=True),
        sa.Column("so_luong", sa.Numeric(15, 2), nullable=False),
        sa.Column(
            "trang_thai", sa.String(length=16), nullable=False,
            server_default=sa.text("'giu'"),
        ),
        sa.Column("khach_hang", sa.String(length=255), nullable=True),
        sa.Column("ref_type", sa.String(length=24), nullable=True),
        sa.Column("ref_id", sa.String(length=64), nullable=True),
        sa.Column(
            "don_gia_xuat", sa.Numeric(15, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("nguoi", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("xuat_luc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("xuat_boi", sa.String(length=64), nullable=True),
        sa.Column("huy_luc", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="muahang",
    )
    op.create_index(
        "ix_kho_rsv_ma_sp", "kho_reservation", ["ma_sp"], schema="muahang"
    )
    op.create_index(
        "ix_kho_rsv_trang_thai", "kho_reservation", ["trang_thai"], schema="muahang"
    )
    op.create_index(
        "ix_kho_rsv_created", "kho_reservation", ["created_at"], schema="muahang"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_kho_rsv_created", table_name="kho_reservation", schema="muahang"
    )
    op.drop_index(
        "ix_kho_rsv_trang_thai", table_name="kho_reservation", schema="muahang"
    )
    op.drop_index(
        "ix_kho_rsv_ma_sp", table_name="kho_reservation", schema="muahang"
    )
    op.drop_table("kho_reservation", schema="muahang")
