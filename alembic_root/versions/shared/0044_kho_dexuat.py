"""Module Kho GĐ2 — Đề xuất nhập kho (kho_de_xuat + kho_de_xuat_item).

Luồng tự chứa đề xuất → duyệt → nhập kho, SKU-native. KHÔNG đụng pipeline PO bán
hàng. Khi nhập kho → ghi vào muahang.kho_movement (GĐ1) với nguon='de_xuat'.

Adds 2 tables under schema muahang:
    kho_de_xuat        — phiếu đề xuất (ma_dx UNIQUE, trang_thai, cap_duyet, ...)
    kho_de_xuat_item   — dòng đề xuất (FK dx_id → kho_de_xuat.id ON DELETE CASCADE)

Revision ID: 0044_kho_dexuat
Revises: 0043_kho_module
Create Date: 2026-08-24
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0044_kho_dexuat"
down_revision: Union[str, None] = "0043_kho_module"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── kho_de_xuat — phiếu đề xuất nhập kho ───────────────────────────────────
    op.create_table(
        "kho_de_xuat",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ma_dx", sa.String(length=32), nullable=False),
        sa.Column(
            "trang_thai", sa.String(length=16), nullable=False,
            server_default=sa.text("'cho_duyet'"),
        ),
        sa.Column(
            "cap_duyet", sa.String(length=8), nullable=False,
            server_default=sa.text("'tp_mh'"),
        ),
        sa.Column("ncc_id", sa.String(length=64), nullable=True),
        sa.Column("ncc_name", sa.String(length=255), nullable=True),
        sa.Column(
            "tong_tien", sa.Numeric(15, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("ly_do", sa.Text(), nullable=True),
        sa.Column("nguoi_tao", sa.String(length=64), nullable=True),
        sa.Column("duyet_boi", sa.String(length=64), nullable=True),
        sa.Column("duyet_luc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duyet_note", sa.Text(), nullable=True),
        sa.Column("nhap_boi", sa.String(length=64), nullable=True),
        sa.Column("nhap_luc", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ma_dx", name="uq_kho_dx_ma_dx"),
        schema="muahang",
    )
    op.create_index(
        "ix_kho_dx_trang_thai", "kho_de_xuat", ["trang_thai"], schema="muahang"
    )
    op.create_index(
        "ix_kho_dx_created", "kho_de_xuat", ["created_at"], schema="muahang"
    )

    # ── kho_de_xuat_item — dòng đề xuất ────────────────────────────────────────
    op.create_table(
        "kho_de_xuat_item",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dx_id", sa.BigInteger(), nullable=False),
        sa.Column("ma_sp", sa.String(length=64), nullable=False),
        sa.Column("ten_sp", sa.String(length=255), nullable=True),
        sa.Column("so_luong", sa.Numeric(15, 2), nullable=False),
        sa.Column(
            "don_gia", sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["dx_id"], ["muahang.kho_de_xuat.id"],
            ondelete="CASCADE",
        ),
        schema="muahang",
    )
    op.create_index(
        "ix_kho_dxi_dx", "kho_de_xuat_item", ["dx_id"], schema="muahang"
    )


def downgrade() -> None:
    op.drop_index("ix_kho_dxi_dx", table_name="kho_de_xuat_item", schema="muahang")
    op.drop_table("kho_de_xuat_item", schema="muahang")

    op.drop_index("ix_kho_dx_created", table_name="kho_de_xuat", schema="muahang")
    op.drop_index("ix_kho_dx_trang_thai", table_name="kho_de_xuat", schema="muahang")
    op.drop_table("kho_de_xuat", schema="muahang")
