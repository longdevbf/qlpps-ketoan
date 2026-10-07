"""QC theo đơn (Mua Hàng) — checklist template + phiếu QC + kết quả + lỗi.

Adds 5 tables under schema muahang:
    qc_template        — bộ tiêu chí mẫu (phạm vi all|loai_don|nhom_sp|custom)
    qc_template_item   — từng tiêu chí trong template (giai_doan, bắt buộc)
    qc_phieu           — 1 lần chạy QC cho 1 đơn ở 1 giai đoạn (ket_luan, nghiệm thu cuối)
    qc_ket_qua         — kết quả từng tiêu chí (SNAPSHOT tieu_chi từ template_item)
    qc_loi             — lỗi phát hiện + vòng đời rework

Các bảng này là HỢP ĐỒNG ĐỌC cho các app khác (join qua order_id / ref_bao_gia).
Đơn phải có phiếu is_nghiem_thu_cuoi + ket_luan ∈ (dat, dat_dk) mới được chuyển
sang "Đã có hàng" (gate ở muahang.app.routers.orders::change_status).

Revision ID: 0042_qc_module
Revises: 0041_field_visit_photo
Create Date: 2026-07-31
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0042_qc_module"
down_revision: Union[str, None] = "0041_field_visit_photo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── qc_template ──────────────────────────────────────────────────────────
    op.create_table(
        "qc_template",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ten", sa.String(length=200), nullable=False),
        sa.Column("pham_vi_kieu", sa.String(length=16), nullable=False),
        sa.Column("pham_vi_gia_tri", sa.String(length=128), nullable=True),
        sa.Column(
            "active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="muahang",
    )

    # ── qc_template_item ─────────────────────────────────────────────────────
    op.create_table(
        "qc_template_item",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("thu_tu", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("tieu_chi", sa.Text(), nullable=False),
        sa.Column("giai_doan", sa.String(length=24), nullable=False),
        sa.Column(
            "bat_buoc", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("huong_dan", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="muahang",
    )
    op.create_index(
        "ix_qc_tpl_item_template", "qc_template_item", ["template_id"],
        schema="muahang",
    )

    # ── qc_phieu ─────────────────────────────────────────────────────────────
    op.create_table(
        "qc_phieu",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.String(length=32), nullable=False),
        sa.Column("ref_bao_gia", sa.String(length=64), nullable=True),
        sa.Column("ncc_id", sa.String(length=64), nullable=True),
        sa.Column("cong_trinh_id", sa.Integer(), nullable=True),
        sa.Column("template_id", sa.BigInteger(), nullable=True),
        sa.Column("giai_doan", sa.String(length=24), nullable=False),
        sa.Column("ket_luan", sa.String(length=16), nullable=True),
        sa.Column(
            "is_nghiem_thu_cuoi", sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("nguoi_qc", sa.String(length=64), nullable=True),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="muahang",
    )
    op.create_index(
        "ix_qc_phieu_order_id", "qc_phieu", ["order_id"], schema="muahang",
    )
    op.create_index(
        "ix_qc_phieu_ref_bao_gia", "qc_phieu", ["ref_bao_gia"], schema="muahang",
    )

    # ── qc_ket_qua ───────────────────────────────────────────────────────────
    op.create_table(
        "qc_ket_qua",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("phieu_id", sa.BigInteger(), nullable=False),
        sa.Column("tieu_chi", sa.Text(), nullable=False),
        sa.Column("giai_doan", sa.String(length=24), nullable=True),
        sa.Column("ket_qua", sa.String(length=8), nullable=True),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="muahang",
    )
    op.create_index(
        "ix_qc_ket_qua_phieu", "qc_ket_qua", ["phieu_id"], schema="muahang",
    )

    # ── qc_loi ───────────────────────────────────────────────────────────────
    op.create_table(
        "qc_loi",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("phieu_id", sa.BigInteger(), nullable=True),
        sa.Column("order_id", sa.String(length=32), nullable=False),
        sa.Column("ref_bao_gia", sa.String(length=64), nullable=True),
        sa.Column("tieu_chi", sa.Text(), nullable=True),
        sa.Column("mo_ta", sa.Text(), nullable=False),
        sa.Column("muc_do", sa.String(length=16), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column(
            "trang_thai", sa.String(length=16), nullable=False,
            server_default=sa.text("'moi'"),
        ),
        sa.Column("nguoi_tao", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="muahang",
    )
    op.create_index(
        "ix_qc_loi_order_id", "qc_loi", ["order_id"], schema="muahang",
    )
    op.create_index(
        "ix_qc_loi_trang_thai", "qc_loi", ["trang_thai"], schema="muahang",
    )


def downgrade() -> None:
    op.drop_index("ix_qc_loi_trang_thai", table_name="qc_loi", schema="muahang")
    op.drop_index("ix_qc_loi_order_id", table_name="qc_loi", schema="muahang")
    op.drop_table("qc_loi", schema="muahang")

    op.drop_index("ix_qc_ket_qua_phieu", table_name="qc_ket_qua", schema="muahang")
    op.drop_table("qc_ket_qua", schema="muahang")

    op.drop_index("ix_qc_phieu_ref_bao_gia", table_name="qc_phieu", schema="muahang")
    op.drop_index("ix_qc_phieu_order_id", table_name="qc_phieu", schema="muahang")
    op.drop_table("qc_phieu", schema="muahang")

    op.drop_index(
        "ix_qc_tpl_item_template", table_name="qc_template_item", schema="muahang"
    )
    op.drop_table("qc_template_item", schema="muahang")

    op.drop_table("qc_template", schema="muahang")
