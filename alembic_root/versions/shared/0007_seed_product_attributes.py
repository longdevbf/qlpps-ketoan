"""Seed shared.product_attributes từ data fix-cứng baogia.

Import 7 loại thuộc tính (phan_khuc, phong_cach, vat_lieu, mau_go, mau_vai,
mau_da, loai_son) cho 3 nhom_master mặc định (Đồ Gỗ / Đồ Mây / Dự Án).

phan_khuc + phong_cach kèm coeff (hệ số nhân giá). 5 loại còn lại coeff
NULL (chỉ là dropdown lựa chọn, không ảnh hưởng giá).

Idempotent: ON CONFLICT DO NOTHING (UniqueConstraint trên triple
(nhom_master, attr_key, attr_value)).

Revision ID: 0007_seed_product_attributes
Revises: 0006_product_attr_coeff
Create Date: 2026-05-06
"""
from typing import Union

from alembic import op


revision: str = "0007_seed_product_attributes"
down_revision: Union[str, None] = "0006_product_attr_coeff"
branch_labels = None
depends_on = None


# (attr_key, attr_value, coeff_or_None)
PHAN_KHUC: list[tuple[str, float | None]] = [
    ("Bản Tiêu Chuẩn", 1.0),
    ("Bản Plus", 1.25),
    ("Hàng Trạm", 0.75),
]

PHONG_CACH: list[tuple[str, float | None]] = [
    ("Rustic", 1.0),
    ("Indochine", 1.4),
    ("Boho", 1.2),
    ("Farmhouse", 1.2),
    ("Me Tây", 1.6),
    ("Gỗ Thịt Tần Bì", 1.2),
    ("Địa Trung Hải", 1.15),
]

VAT_LIEU: list[tuple[str, float | None]] = [
    ("Gỗ sồi (ash)", None),
    ("Plywood phủ veneer sồi", None),
    ("Mặt kính cường lực", None),
    ("Mặt kính thường", None),
    ("Mút K43", None),
    ("Mút Việt Nhật", None),
    ("Mút K24", None),
    ("Mây nhựa", None),
    ("Mây tự nhiên", None),
    ("Cói", None),
    ("Lục Bình", None),
]

MAU_GO: list[tuple[str, float | None]] = [
    (f"Màu {i}", None) for i in range(1, 10)
]

LOAI_SON: list[tuple[str, float | None]] = [
    ("07", None),
    ("Incherm", None),
]

MAU_VAI: list[tuple[str, float | None]] = [
    ("Cleo 01", None),
    ("Be", None),
    ("Nâu", None),
    ("Xám", None),
    ("Trắng", None),
]

MAU_DA: list[tuple[str, float | None]] = [
    ("Đen", None),
    ("Nâu", None),
    ("Be", None),
    ("Bò sáp", None),
]

# attr_key → list[(value, coeff)]
ALL_KEYS: dict[str, list[tuple[str, float | None]]] = {
    "phan_khuc": PHAN_KHUC,
    "phong_cach": PHONG_CACH,
    "vat_lieu": VAT_LIEU,
    "mau_go": MAU_GO,
    "mau_vai": MAU_VAI,
    "mau_da": MAU_DA,
    "loai_son": LOAI_SON,
}

NHOM_MASTERS = ["Đồ Gỗ", "Đồ Mây", "Dự Án"]


def upgrade() -> None:
    conn = op.get_bind()
    rows = []
    for nm in NHOM_MASTERS:
        for key, items in ALL_KEYS.items():
            for idx, (val, coeff) in enumerate(items):
                rows.append({
                    "nhom_master": nm,
                    "attr_key": key,
                    "attr_value": val,
                    "coeff": coeff,
                    "thu_tu": (idx + 1) * 10,
                    "active": True,
                })
    if not rows:
        return

    # ON CONFLICT DO NOTHING — idempotent re-runs (Postgres only).
    from sqlalchemy import text
    sql = text(
        """
        INSERT INTO shared.product_attributes
            (nhom_master, attr_key, attr_value, coeff, thu_tu, active)
        VALUES
            (:nhom_master, :attr_key, :attr_value, :coeff, :thu_tu, :active)
        ON CONFLICT ON CONSTRAINT uq_product_attributes_triple DO NOTHING
        """
    )
    for r in rows:
        conn.execute(sql, r)


def downgrade() -> None:
    # Xoá đúng các row seed (theo nhom_master + attr_key) — không xoá
    # row do user thêm sau này (khác triple).
    conn = op.get_bind()
    from sqlalchemy import text
    seeded_values: dict[tuple[str, str], list[str]] = {}
    for nm in NHOM_MASTERS:
        for key, items in ALL_KEYS.items():
            seeded_values[(nm, key)] = [v for v, _ in items]
    sql = text(
        """
        DELETE FROM shared.product_attributes
        WHERE nhom_master = :nhom_master
          AND attr_key = :attr_key
          AND attr_value = ANY(:values)
        """
    )
    for (nm, key), values in seeded_values.items():
        conn.execute(sql, {"nhom_master": nm, "attr_key": key, "values": values})
