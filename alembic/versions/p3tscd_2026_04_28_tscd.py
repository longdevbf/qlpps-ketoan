"""Phase 3 — Tài Sản Cố Định + Khấu Hao (đường thẳng).

Module TSCĐ:
  - tai_san_co_dinh: master 1 TSCĐ (mã, tên, loại, nhóm, nguyên giá, số tháng KH,
    hao mòn lũy kế, account_code, bộ phận, trạng thái...).
  - khau_hao_log: nhật ký khấu hao tháng (mỗi TSCĐ × tháng = 1 dòng), link journal_id.

Quy ước Papasan:
  - Phương pháp khấu hao đường thẳng (straight-line) — SME phân phối.
  - Account TT200: 211 (TSCĐ HH), 213 (vô hình), 214 (hao mòn lũy kế),
    641 (CP BH) / 642 (CP QL) cho khấu hao tuỳ bộ phận.
  - Mỗi giao dịch TSCĐ post 1 journal entry tự động qua services/journal.py.

Revision ID: p3tscd_2026_04_28
Revises: 0fb99389aa26
Create Date: 2026-04-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p3tscd_2026_04_28"
down_revision: Union[str, None] = "0fb99389aa26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── tai_san_co_dinh ────────────────────────────────────────────────────
    op.create_table(
        "tai_san_co_dinh",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ma_tscd", sa.String(32), nullable=False),
        sa.Column("ten_tscd", sa.String(255), nullable=False),
        sa.Column(
            "loai", sa.String(20),
            server_default="huu_hinh", nullable=False,
        ),  # huu_hinh | vo_hinh
        sa.Column("nhom", sa.String(64), nullable=True),
        sa.Column("ngay_mua", sa.Date(), nullable=False),
        sa.Column("ngay_su_dung", sa.Date(), nullable=False),
        sa.Column(
            "nguyen_gia", sa.Numeric(15, 2), nullable=False,
        ),
        sa.Column("so_thang_kh", sa.Integer(), nullable=False),
        sa.Column(
            "phuong_phap", sa.String(20),
            server_default="duong_thang", nullable=False,
        ),
        sa.Column(
            "hao_mon_luy_ke", sa.Numeric(15, 2),
            server_default="0", nullable=False,
        ),
        sa.Column(
            "account_code", sa.String(20),
            server_default="211", nullable=False,
        ),
        sa.Column(
            "bo_phan", sa.String(20),
            server_default="quan_ly", nullable=False,
        ),  # ban_hang | quan_ly | tai_chinh | khac
        sa.Column("ncc", sa.String(255), nullable=True),
        sa.Column("source_doc_id", sa.String(64), nullable=True),
        sa.Column(
            "trang_thai", sa.String(20),
            server_default="dang_su_dung", nullable=False,
        ),  # dang_su_dung | da_thanh_ly | hong
        sa.Column("ngay_thanh_ly", sa.Date(), nullable=True),
        sa.Column("gia_thanh_ly", sa.Numeric(15, 2), nullable=True),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("hinh_anh", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("ma_tscd", name="uq_tscd_ma"),
        sa.CheckConstraint("nguyen_gia > 0", name="ck_tscd_nguyen_gia_pos"),
        sa.CheckConstraint("so_thang_kh > 0", name="ck_tscd_so_thang_pos"),
        schema="ketoan",
    )
    op.create_index(
        "ix_tscd_loai", "tai_san_co_dinh", ["loai"], schema="ketoan",
    )
    op.create_index(
        "ix_tscd_trang_thai", "tai_san_co_dinh",
        ["trang_thai"], schema="ketoan",
    )
    op.create_index(
        "ix_tscd_nhom", "tai_san_co_dinh", ["nhom"], schema="ketoan",
    )

    # ─── khau_hao_log ───────────────────────────────────────────────────────
    op.create_table(
        "khau_hao_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tscd_id", sa.Integer(), nullable=False),
        sa.Column("thang", sa.String(7), nullable=False),  # YYYY-MM
        sa.Column("so_tien", sa.Numeric(15, 2), nullable=False),
        sa.Column(
            "hao_mon_luy_ke_sau", sa.Numeric(15, 2), nullable=False,
        ),
        sa.Column("journal_id", sa.Integer(), nullable=True),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tscd_id"], ["ketoan.tai_san_co_dinh.id"],
            name="fk_kh_tscd", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tscd_id", "thang", name="uq_kh_tscd_thang"),
        sa.CheckConstraint("so_tien > 0", name="ck_kh_so_tien_pos"),
        schema="ketoan",
    )
    op.create_index(
        "ix_kh_thang", "khau_hao_log", ["thang"], schema="ketoan",
    )
    op.create_index(
        "ix_kh_tscd", "khau_hao_log", ["tscd_id"], schema="ketoan",
    )


def downgrade() -> None:
    op.drop_index("ix_kh_tscd", table_name="khau_hao_log", schema="ketoan")
    op.drop_index("ix_kh_thang", table_name="khau_hao_log", schema="ketoan")
    op.drop_table("khau_hao_log", schema="ketoan")

    op.drop_index(
        "ix_tscd_nhom", table_name="tai_san_co_dinh", schema="ketoan",
    )
    op.drop_index(
        "ix_tscd_trang_thai", table_name="tai_san_co_dinh", schema="ketoan",
    )
    op.drop_index(
        "ix_tscd_loai", table_name="tai_san_co_dinh", schema="ketoan",
    )
    op.drop_table("tai_san_co_dinh", schema="ketoan")
