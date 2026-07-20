"""Vốn Chủ Sở Hữu + Quỹ DN + TK NH giao dịch (M4 — overnight 2026-04-28)

Module Vốn Chủ Sở Hữu (VCSH) + nhật ký giao dịch tài khoản ngân hàng:
  - von_chu_so_huu: nhật ký gop_von / rut_von / chia_co_tuc / trich_quy / dieu_chinh
  - quy_dn: danh mục quỹ DN (đầu tư phát triển, dự phòng tài chính, khen thưởng phúc lợi)
  - tai_khoan_nh_giao_dich: nhật ký thu/chi cho từng tài khoản ngân hàng — số dư
    chạy = SUM(thu) - SUM(chi) (bỏ pattern lưu cột so_du cứng).

Revision ID: m4vc_2026_04_28
Revises: <M1_PLACEHOLDER>     # rebase khi merge với M1
Create Date: 2026-04-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m4vc_2026_04_28"
down_revision: Union[str, None] = "m3pl_2026_04_28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── von_chu_so_huu ────────────────────────────────────────────────────
    op.create_table(
        "von_chu_so_huu",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ngay", sa.Date(), nullable=False),
        # gop_von | rut_von | chia_co_tuc | trich_quy | dieu_chinh
        sa.Column("loai_giao_dich", sa.String(20), nullable=False),
        sa.Column("so_tien", sa.Numeric(15, 2), nullable=False),
        sa.Column("chu_so_huu", sa.String(128), nullable=True),
        sa.Column("quy_id", sa.Integer(), nullable=True),  # link sang quy_dn khi loai='trich_quy'
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("source_doc_id", sa.String(64), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        schema="ketoan",
    )
    op.create_index(
        "ix_voncsh_ngay", "von_chu_so_huu", ["ngay"], schema="ketoan",
    )
    op.create_index(
        "ix_voncsh_loai", "von_chu_so_huu", ["loai_giao_dich"], schema="ketoan",
    )

    # ─── quy_dn ────────────────────────────────────────────────────────────
    op.create_table(
        "quy_dn",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ten_quy", sa.String(128), nullable=False),
        sa.Column(
            "so_du", sa.Numeric(15, 2),
            server_default="0", nullable=False,
        ),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column(
            "active", sa.Boolean(),
            server_default=sa.true(), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("ten_quy", name="uq_quy_dn_ten"),
        schema="ketoan",
    )

    # FK voncsh -> quy_dn (sau khi quy_dn tồn tại)
    op.create_foreign_key(
        "fk_voncsh_quy_dn",
        source_schema="ketoan", source_table="von_chu_so_huu",
        referent_schema="ketoan", referent_table="quy_dn",
        local_cols=["quy_id"], remote_cols=["id"],
        ondelete="SET NULL",
    )

    # ─── tai_khoan_nh_giao_dich ────────────────────────────────────────────
    op.create_table(
        "tai_khoan_nh_giao_dich",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ngay", sa.Date(), nullable=False),
        sa.Column("tai_khoan_id", sa.Integer(), nullable=False),
        # 'thu' | 'chi'
        sa.Column("loai", sa.String(10), nullable=False),
        sa.Column("so_tien", sa.Numeric(15, 2), nullable=False),
        sa.Column("doi_tac", sa.String(255), nullable=True),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("source_app", sa.String(32), nullable=True),
        sa.Column("source_doc_id", sa.String(64), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tai_khoan_id"], ["ketoan.tai_khoan_nh.id"],
            name="fk_tknhgd_tai_khoan_nh", ondelete="CASCADE",
        ),
        schema="ketoan",
    )
    op.create_index(
        "ix_tknh_gd_ngay", "tai_khoan_nh_giao_dich", ["ngay"], schema="ketoan",
    )
    op.create_index(
        "ix_tknh_gd_tk", "tai_khoan_nh_giao_dich",
        ["tai_khoan_id"], schema="ketoan",
    )

    # ─── Seed quy_dn mặc định ──────────────────────────────────────────────
    op.execute("""
        INSERT INTO ketoan.quy_dn (ten_quy, so_du, ghi_chu, active)
        VALUES
            ('Quỹ đầu tư phát triển', 0, 'Quỹ tái đầu tư phát triển doanh nghiệp', true),
            ('Quỹ dự phòng tài chính', 0, 'Quỹ dự phòng rủi ro tài chính', true),
            ('Quỹ khen thưởng phúc lợi', 0, 'Quỹ khen thưởng + phúc lợi nhân viên', true)
        ON CONFLICT (ten_quy) DO NOTHING;
    """)


def downgrade() -> None:
    op.drop_index(
        "ix_tknh_gd_tk",
        table_name="tai_khoan_nh_giao_dich", schema="ketoan",
    )
    op.drop_index(
        "ix_tknh_gd_ngay",
        table_name="tai_khoan_nh_giao_dich", schema="ketoan",
    )
    op.drop_table("tai_khoan_nh_giao_dich", schema="ketoan")

    op.drop_constraint(
        "fk_voncsh_quy_dn",
        table_name="von_chu_so_huu", schema="ketoan", type_="foreignkey",
    )
    op.drop_table("quy_dn", schema="ketoan")

    op.drop_index(
        "ix_voncsh_loai",
        table_name="von_chu_so_huu", schema="ketoan",
    )
    op.drop_index(
        "ix_voncsh_ngay",
        table_name="von_chu_so_huu", schema="ketoan",
    )
    op.drop_table("von_chu_so_huu", schema="ketoan")
