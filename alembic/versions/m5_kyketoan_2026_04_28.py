"""Kỳ Kế Toán + P&L Snapshot + Lợi Nhuận Giữ Lại.

Module Đóng Kỳ Kế Toán (Period Close):
  - bao_cao_pl_snapshot: snapshot full P&L theo tháng (10 chỉ tiêu chuẩn mực + breakdown JSONB)
  - ky_ke_toan: trạng thái kỳ (đang_mở/đã_chốt) + LN giữ lại đầu kỳ / cuối kỳ + cổ tức + trích quỹ

Quy ước Papasan:
  - Năm tài chính dương lịch (1/1 → 31/12)
  - Đóng kỳ theo tháng (`thang VARCHAR(7)` định dạng 'YYYY-MM')
  - Sau khi chốt: chặn CRUD số liệu thuộc kỳ đó (validate ở level service)
  - LN giữ lại = LN đầu kỳ + LNST kỳ - cổ tức - trích quỹ

Revision ID: m5kk_2026_04_28
Revises: M5_PLACEHOLDER
Create Date: 2026-04-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "m5kk_2026_04_28"
down_revision: Union[str, None] = "m4vc_2026_04_28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── bao_cao_pl_snapshot ──────────────────────────────────────────────────
    op.create_table(
        "bao_cao_pl_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thang", sa.String(7), nullable=False),  # 'YYYY-MM'
        sa.Column("dt_thuan", sa.Numeric(15, 2), nullable=True),
        sa.Column("cogs", sa.Numeric(15, 2), nullable=True),
        sa.Column("ln_gop", sa.Numeric(15, 2), nullable=True),
        sa.Column("cp_ban_hang", sa.Numeric(15, 2), nullable=True),
        sa.Column("cp_quan_ly", sa.Numeric(15, 2), nullable=True),
        sa.Column("dt_tai_chinh", sa.Numeric(15, 2), nullable=True),
        sa.Column("cp_tai_chinh", sa.Numeric(15, 2), nullable=True),
        sa.Column("thu_nhap_khac", sa.Numeric(15, 2), nullable=True),
        sa.Column("cp_khac", sa.Numeric(15, 2), nullable=True),
        sa.Column("ln_truoc_thue", sa.Numeric(15, 2), nullable=True),
        sa.Column("thue_tndn", sa.Numeric(15, 2), nullable=True),
        sa.Column("lnst", sa.Numeric(15, 2), nullable=True),
        sa.Column("raw_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("thang", name="uq_pl_snapshot_thang"),
        schema="ketoan",
    )
    op.create_index(
        "ix_pl_snapshot_thang", "bao_cao_pl_snapshot", ["thang"], schema="ketoan",
    )

    # ─── ky_ke_toan ───────────────────────────────────────────────────────────
    op.create_table(
        "ky_ke_toan",
        sa.Column("thang", sa.String(7), primary_key=True),  # 'YYYY-MM'
        sa.Column(
            "trang_thai", sa.String(20),
            nullable=False, server_default="dang_mo",
        ),
        sa.Column("chot_luc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chot_boi", sa.String(64), nullable=True),
        sa.Column("pl_snapshot_id", sa.Integer(), nullable=True),
        sa.Column(
            "ln_giu_lai_dau_ky", sa.Numeric(15, 2),
            nullable=True, server_default="0",
        ),
        sa.Column("lnst_ky", sa.Numeric(15, 2), nullable=True),
        sa.Column("ln_giu_lai_cuoi_ky", sa.Numeric(15, 2), nullable=True),
        sa.Column(
            "co_tuc_da_chia", sa.Numeric(15, 2),
            nullable=True, server_default="0",
        ),
        sa.Column(
            "trich_quy_ky", sa.Numeric(15, 2),
            nullable=True, server_default="0",
        ),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["pl_snapshot_id"], ["ketoan.bao_cao_pl_snapshot.id"],
            name="fk_kkt_pl_snapshot", ondelete="SET NULL",
        ),
        schema="ketoan",
    )
    op.create_index(
        "ix_kkt_trang_thai", "ky_ke_toan", ["trang_thai"], schema="ketoan",
    )


def downgrade() -> None:
    op.drop_index("ix_kkt_trang_thai", table_name="ky_ke_toan", schema="ketoan")
    op.drop_table("ky_ke_toan", schema="ketoan")
    op.drop_index(
        "ix_pl_snapshot_thang", table_name="bao_cao_pl_snapshot", schema="ketoan",
    )
    op.drop_table("bao_cao_pl_snapshot", schema="ketoan")
