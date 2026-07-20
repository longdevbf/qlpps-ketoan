"""Q2 — Bảng giao dịch quỹ DN (audit trail thu/chi).

Cấu trúc:
- `quy_dn_giao_dich` — log từng lần nạp/chi quỹ.
- Mọi thay đổi `quy_dn.so_du` PHẢI đi qua bảng này (qua service `quy_dn_calc`)
  để có thể recalc + void.

Indexes:
- ix_qdgd_quy        (quy_id)
- ix_qdgd_ngay       (ngay)
- ix_qdgd_source     (source_type, source_id)

Revision ID: q2_2026_04_29_quy_giao_dich
Revises: p7g_2026_04_29_backfill_cf
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "q2_2026_04_29_quy_giao_dich"
down_revision: Union[str, None] = "p7g_2026_04_29_backfill_cf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quy_dn_giao_dich",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "quy_id", sa.Integer(), nullable=False,
        ),
        sa.Column("ngay", sa.Date(), nullable=False),
        sa.Column("loai", sa.String(10), nullable=False),
        sa.Column("so_tien", sa.Numeric(15, 2), nullable=False),
        sa.Column("noi_dung", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(32), nullable=True),
        sa.Column("source_id", sa.String(64), nullable=True),
        sa.Column("tai_khoan_id", sa.Integer(), nullable=True),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["quy_id"], ["ketoan.quy_dn.id"],
            ondelete="CASCADE", name="fk_qdgd_quy",
        ),
        sa.CheckConstraint("loai IN ('thu','chi')", name="ck_qdgd_loai"),
        sa.CheckConstraint("so_tien > 0", name="ck_qdgd_so_tien_pos"),
        schema="ketoan",
    )
    op.create_index(
        "ix_qdgd_quy", "quy_dn_giao_dich", ["quy_id"], schema="ketoan",
    )
    op.create_index(
        "ix_qdgd_ngay", "quy_dn_giao_dich", ["ngay"], schema="ketoan",
    )
    op.create_index(
        "ix_qdgd_source", "quy_dn_giao_dich",
        ["source_type", "source_id"], schema="ketoan",
    )


def downgrade() -> None:
    op.drop_index("ix_qdgd_source", table_name="quy_dn_giao_dich", schema="ketoan")
    op.drop_index("ix_qdgd_ngay", table_name="quy_dn_giao_dich", schema="ketoan")
    op.drop_index("ix_qdgd_quy", table_name="quy_dn_giao_dich", schema="ketoan")
    op.drop_table("quy_dn_giao_dich", schema="ketoan")
