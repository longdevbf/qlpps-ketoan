"""Field visit photos — ảnh "Công tác xưởng" NV Mua Hàng chụp tại xưởng NCC.

Adds table muahang.field_visit_photo: ảnh sản phẩm theo đơn (mộc / sơn hoàn
thiện / đóng gói / lỗi) để KD & Sale Admin thấy tình trạng thật. Ảnh lỗi
(is_defect) hiển thị cho CEO ở Cockpit.

Bảng này là HỢP ĐỒNG ĐỌC cho các app khác (KD/SaleAdmin join qua ref_bao_gia).

Revision ID: 0041_field_visit_photo
Revises: 0040_mh_kpi_giao_van_feature
Create Date: 2026-07-27
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0041_field_visit_photo"
down_revision: Union[str, None] = "0040_mh_kpi_giao_van_feature"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "field_visit_photo",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("cong_trinh_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(length=32), nullable=False),
        sa.Column("ref_bao_gia", sa.String(length=64), nullable=True),
        sa.Column("ncc_id", sa.String(length=64), nullable=True),
        sa.Column("giai_doan", sa.String(length=24), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column(
            "is_defect", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("van_de_id", sa.String(length=64), nullable=True),
        sa.Column("nguoi_chup", sa.String(length=64), nullable=True),
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
        "ix_fvp_order_id", "field_visit_photo", ["order_id"], schema="muahang",
    )
    op.create_index(
        "ix_fvp_ref_bao_gia", "field_visit_photo", ["ref_bao_gia"], schema="muahang",
    )
    op.create_index(
        "ix_fvp_cong_trinh_id", "field_visit_photo", ["cong_trinh_id"], schema="muahang",
    )
    op.create_index(
        "ix_fvp_is_defect", "field_visit_photo", ["is_defect"], schema="muahang",
    )


def downgrade() -> None:
    op.drop_index("ix_fvp_is_defect", table_name="field_visit_photo", schema="muahang")
    op.drop_index(
        "ix_fvp_cong_trinh_id", table_name="field_visit_photo", schema="muahang"
    )
    op.drop_index(
        "ix_fvp_ref_bao_gia", table_name="field_visit_photo", schema="muahang"
    )
    op.drop_index("ix_fvp_order_id", table_name="field_visit_photo", schema="muahang")
    op.drop_table("field_visit_photo", schema="muahang")
