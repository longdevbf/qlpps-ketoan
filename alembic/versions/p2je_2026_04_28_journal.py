"""Phase 2 — Double-Entry Journal (sổ nhật ký bút toán nợ–có).

Module Bút Toán Kế Toán:
  - journal_entry: header (mã bút toán, ngày, tổng tiền, source/source_id, trạng thái)
  - journal_line: chi tiết các dòng nợ/có (account_code TT200 + ref_table/ref_id soft FK)

Quy ước Papasan:
  - Mỗi nghiệp vụ CRUD manual (góp vốn, chi phí, nhập kho, vay, ...) phải post 1 JE
    với nợ = có (tolerance 0.01).
  - Account code theo TT200: 111/112/131/156/211/311/331/334/341/411/414/415/353/421/511/632/635/641/642/711/811/821.
  - source_type giúp truy vết nguồn gốc bút toán (gop_von | chi_phi_phat_sinh | ...).

Revision ID: p2je_2026_04_28
Revises: m2bom_2026_04_28
Create Date: 2026-04-28

NOTE: yêu cầu nguyên gốc revises='m5kk_2026_04_28', nhưng agent BOM (M2) đã
chiếm slot đó (m2bom.down=m5kk) → để tránh 2 head nhánh song song, P2 chain
SAU m2bom (m5kk → m2bom → p2je). Cả 2 module độc lập DDL nên thứ tự không
ảnh hưởng schema.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p2je_2026_04_28"
down_revision: Union[str, None] = "m2bom_2026_04_28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── journal_entry (header) ──────────────────────────────────────────────
    op.create_table(
        "journal_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ma_but_toan", sa.String(32), nullable=False),
        sa.Column("ngay", sa.Date(), nullable=False),
        sa.Column("mo_ta", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(40), nullable=True),
        sa.Column("source_id", sa.String(64), nullable=True),
        sa.Column("tong_tien", sa.Numeric(15, 2), nullable=False),
        sa.Column(
            "trang_thai", sa.String(20),
            server_default="da_post", nullable=False,
        ),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("ma_but_toan", name="uq_je_ma_but_toan"),
        schema="ketoan",
    )
    op.create_index(
        "ix_je_ngay", "journal_entry", ["ngay"], schema="ketoan",
    )
    op.create_index(
        "ix_je_source", "journal_entry",
        ["source_type", "source_id"], schema="ketoan",
    )

    # ─── journal_line (chi tiết) ─────────────────────────────────────────────
    op.create_table(
        "journal_line",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("journal_id", sa.Integer(), nullable=False),
        sa.Column("loai", sa.String(10), nullable=False),  # 'no' | 'co'
        sa.Column("account_code", sa.String(20), nullable=False),
        sa.Column("account_name", sa.String(255), nullable=True),
        sa.Column("ref_table", sa.String(64), nullable=True),
        sa.Column("ref_id", sa.Integer(), nullable=True),
        sa.Column("so_tien", sa.Numeric(15, 2), nullable=False),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["journal_id"], ["ketoan.journal_entry.id"],
            name="fk_jl_journal", ondelete="CASCADE",
        ),
        schema="ketoan",
    )
    op.create_index(
        "ix_jl_journal", "journal_line", ["journal_id"], schema="ketoan",
    )
    op.create_index(
        "ix_jl_account", "journal_line", ["account_code"], schema="ketoan",
    )
    op.create_index(
        "ix_jl_ref", "journal_line",
        ["ref_table", "ref_id"], schema="ketoan",
    )


def downgrade() -> None:
    op.drop_index("ix_jl_ref", table_name="journal_line", schema="ketoan")
    op.drop_index("ix_jl_account", table_name="journal_line", schema="ketoan")
    op.drop_index("ix_jl_journal", table_name="journal_line", schema="ketoan")
    op.drop_table("journal_line", schema="ketoan")

    op.drop_index("ix_je_source", table_name="journal_entry", schema="ketoan")
    op.drop_index("ix_je_ngay", table_name="journal_entry", schema="ketoan")
    op.drop_table("journal_entry", schema="ketoan")
