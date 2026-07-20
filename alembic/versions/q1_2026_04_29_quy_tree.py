"""Mở rộng quy_dn thành cây + seed 17 quỹ.

Cấu trúc cây:
- Root nodes: Rủi Ro / Động Lực / Phúc Lợi / Công Đoàn / Công Ty
- Sub: phân bổ con (vị trí cho Động Lực, hoạt động cho Phúc Lợi/VHDN)

Thêm 4 cột:
- parent_id        — FK self, NULL = root
- nguon_compute    — 'manual' | 'doanh_thu_pct' | 'parent_pct' | 'hcns_cong_doan'
- ty_le_pct        — % trên DT (cho root) hoặc % trên parent (cho child)
- thu_tu           — sort order trong cùng level

Revision ID: q1_2026_04_29
Revises: p6a_2026_04_29
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "q1_2026_04_29"
down_revision: Union[str, None] = "p6a_2026_04_29"
branch_labels = None
depends_on = None


# Cây quỹ seed — (ten, parent_ten, nguon, ty_le_pct, thu_tu, ghi_chu)
# Với nguon='doanh_thu_pct' → ty_le_pct là % trên DT (VD 0.5 = 0.5%)
# Với nguon='parent_pct'    → ty_le_pct là % trên quỹ parent (VD 33 = 33%)
# Với nguon='hcns_cong_doan' / 'manual' → ty_le_pct = 0
SEED_TREE = [
    # Root quỹ — KHÔNG seed "Quỹ Động Lực Làm Việc" (anh bỏ 2026-04-29
    # vì khoản này đã nằm trong lương HCNS)
    ("Quỹ Rủi Ro",            None,                "doanh_thu_pct", 0.5,  10, "Trích 0.5% DT — phòng rủi ro chung"),
    ("Quỹ Phúc Lợi",          None,                "doanh_thu_pct", 1.2,  30, "Phân bổ Thưởng/VHDN/Đào tạo/Yearend"),
    ("Quỹ Công Đoàn",         None,                "hcns_cong_doan", 0,   40, "Đọc từ HCNS payroll (read-only)"),
    ("Quỹ Công Ty",           None,                "manual",         0,   50, "Quỹ tổng hợp tự do"),
    # Phúc lợi — 4 nhánh con
    ("Thưởng Cả Năm",         "Quỹ Phúc Lợi",          "parent_pct", 68, 10, ""),
    ("Văn Hóa Doanh Nghiệp",  "Quỹ Phúc Lợi",          "parent_pct", 22, 20, "Phân bổ Du lịch / HĐVH / Vinh danh"),
    ("Đào Tạo",               "Quỹ Phúc Lợi",          "parent_pct",  5, 30, ""),
    ("Year-end Party",        "Quỹ Phúc Lợi",          "parent_pct",  5, 40, ""),
    # VHDN — 3 hoạt động
    ("Du Lịch",               "Văn Hóa Doanh Nghiệp",  "parent_pct", 50, 10, ""),
    ("Hoạt Động Văn Hóa",     "Văn Hóa Doanh Nghiệp",  "parent_pct", 15, 20, ""),
    ("Vinh Danh",             "Văn Hóa Doanh Nghiệp",  "parent_pct", 35, 30, ""),
]


def upgrade() -> None:
    op.add_column("quy_dn", sa.Column("parent_id", sa.Integer(), nullable=True), schema="ketoan")
    op.add_column(
        "quy_dn",
        sa.Column("nguon_compute", sa.String(32), nullable=False, server_default="manual"),
        schema="ketoan",
    )
    op.add_column(
        "quy_dn",
        sa.Column("ty_le_pct", sa.Numeric(7, 4), nullable=False, server_default="0"),
        schema="ketoan",
    )
    op.add_column(
        "quy_dn",
        sa.Column("thu_tu", sa.Integer(), nullable=False, server_default="0"),
        schema="ketoan",
    )
    op.create_foreign_key(
        "fk_quy_dn_parent",
        "quy_dn", "quy_dn",
        ["parent_id"], ["id"],
        source_schema="ketoan", referent_schema="ketoan",
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_quy_dn_parent", "quy_dn", ["parent_id"], schema="ketoan"
    )

    # Seed cây quỹ — 2 pass: root trước, child sau
    conn = op.get_bind()

    # Pass 1: insert root nodes (parent_id NULL). Idempotent: skip nếu đã tồn tại.
    name_to_id: dict[str, int] = {}
    existing = conn.execute(sa.text(
        "SELECT id, ten_quy FROM ketoan.quy_dn"
    )).fetchall()
    for r in existing:
        name_to_id[r[1]] = r[0]

    for ten, parent, nguon, pct, thu_tu, gc in SEED_TREE:
        if parent is not None:
            continue
        if ten in name_to_id:
            # Update các cột mới cho row có sẵn
            conn.execute(sa.text("""
                UPDATE ketoan.quy_dn
                SET nguon_compute = :n, ty_le_pct = :p, thu_tu = :t, ghi_chu = :gc
                WHERE id = :id
            """), {"n": nguon, "p": pct, "t": thu_tu, "gc": gc, "id": name_to_id[ten]})
            continue
        result = conn.execute(sa.text("""
            INSERT INTO ketoan.quy_dn (ten_quy, so_du, ghi_chu, active, nguon_compute, ty_le_pct, thu_tu)
            VALUES (:ten, 0, :gc, true, :n, :p, :t) RETURNING id
        """), {"ten": ten, "gc": gc, "n": nguon, "p": pct, "t": thu_tu})
        name_to_id[ten] = result.scalar()

    # Pass 2: insert child nodes
    for ten, parent, nguon, pct, thu_tu, gc in SEED_TREE:
        if parent is None:
            continue
        if ten in name_to_id:
            conn.execute(sa.text("""
                UPDATE ketoan.quy_dn
                SET parent_id = :pid, nguon_compute = :n, ty_le_pct = :p, thu_tu = :t, ghi_chu = :gc
                WHERE id = :id
            """), {"pid": name_to_id[parent], "n": nguon, "p": pct, "t": thu_tu, "gc": gc, "id": name_to_id[ten]})
            continue
        result = conn.execute(sa.text("""
            INSERT INTO ketoan.quy_dn (ten_quy, so_du, ghi_chu, active, parent_id, nguon_compute, ty_le_pct, thu_tu)
            VALUES (:ten, 0, :gc, true, :pid, :n, :p, :t) RETURNING id
        """), {
            "ten": ten, "gc": gc,
            "pid": name_to_id[parent],
            "n": nguon, "p": pct, "t": thu_tu,
        })
        name_to_id[ten] = result.scalar()


def downgrade() -> None:
    # Xoá child trước (CASCADE cũng OK), giữ data root cũ (3 quỹ VAS gốc)
    op.execute("""
        DELETE FROM ketoan.quy_dn WHERE parent_id IS NOT NULL
        OR ten_quy IN (
            'Quỹ Rủi Ro', 'Quỹ Phúc Lợi',
            'Quỹ Công Đoàn', 'Quỹ Công Ty'
        )
    """)
    op.drop_index("ix_quy_dn_parent", table_name="quy_dn", schema="ketoan")
    op.drop_constraint("fk_quy_dn_parent", "quy_dn", schema="ketoan")
    op.drop_column("quy_dn", "thu_tu", schema="ketoan")
    op.drop_column("quy_dn", "ty_le_pct", schema="ketoan")
    op.drop_column("quy_dn", "nguon_compute", schema="ketoan")
    op.drop_column("quy_dn", "parent_id", schema="ketoan")
