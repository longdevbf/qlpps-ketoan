"""M1 Inventory data backfill — port từ muahang.ton_kho_items.

Thực hiện:
  1. Distinct danh_muc (từ muahang.ton_kho_items) → ketoan.product_category
     (parent NULL — dùng tạm flat list, manager có thể tổ chức cây sau).
  2. Distinct (ma_sp, ten_sp, danh_muc, dvt) → ketoan.product
     - ma_sp NULL → fallback slug từ ten_sp (uppercase, alnum + dash, max 48).
     - dvt mặc định 'cái' (muahang.ton_kho_items không có dvt riêng → infer 'cái').
  3. Mỗi row ton_kho_items → 1 inventory_movement(loai='nhap')
     (chronological theo ngay_nhap, fallback created_at::date, fallback today).
  4. Recalc inventory_balance bằng replay chronological → bình quân gia quyền.

Idempotent — KHÔNG insert lại nếu đã tồn tại
(check ma_nhom uniq, ma_sp uniq, source_app+source_doc_id uniq).

Revision ID: m1inv_data_2026_04_28
Revises: m1inv_2026_04_28
Create Date: 2026-04-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m1inv_data_2026_04_28"
down_revision: Union[str, None] = "m1inv_2026_04_28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _slugify(s: str, fallback: str = "SP") -> str:
    out = []
    for ch in (s or "").upper():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("-")
    slug = "".join(out)[:48].strip("-")
    return slug or fallback


def upgrade() -> None:
    bind = op.get_bind()
    # Bỏ qua nếu schema muahang chưa có ton_kho_items
    has_src = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='muahang' AND table_name='ton_kho_items'"
    )).first()
    if not has_src:
        return

    # ─── 1. Backfill product_category từ distinct danh_muc ──────────────────
    rows = bind.execute(sa.text("""
        SELECT DISTINCT danh_muc
        FROM muahang.ton_kho_items
        WHERE danh_muc IS NOT NULL AND TRIM(danh_muc) <> ''
    """)).fetchall()

    cat_map: dict[str, int] = {}  # ten_nhom → category_id
    for (dm,) in rows:
        ma_nhom = _slugify(dm, "NHOM")[:32]
        existing = bind.execute(sa.text(
            "SELECT id FROM ketoan.product_category WHERE ma_nhom = :m"
        ), {"m": ma_nhom}).first()
        if existing:
            cat_map[dm] = existing[0]
            continue
        result = bind.execute(sa.text("""
            INSERT INTO ketoan.product_category(ma_nhom, ten_nhom, parent_id, display_order, active)
            VALUES (:m, :t, NULL, 0, TRUE)
            RETURNING id
        """), {"m": ma_nhom, "t": dm})
        cat_map[dm] = result.scalar_one()

    # Default category cho rows danh_muc NULL
    default_cat_id = bind.execute(sa.text(
        "SELECT id FROM ketoan.product_category WHERE ma_nhom = 'KHAC'"
    )).scalar()
    if not default_cat_id:
        default_cat_id = bind.execute(sa.text("""
            INSERT INTO ketoan.product_category(ma_nhom, ten_nhom, parent_id, display_order, active)
            VALUES ('KHAC', 'Khác (auto)', NULL, 999, TRUE)
            RETURNING id
        """)).scalar_one()

    # ─── 2. Backfill product từ distinct (ma_sp/ten_sp/danh_muc) ────────────
    sp_rows = bind.execute(sa.text("""
        SELECT
            COALESCE(NULLIF(TRIM(ma_sp), ''), NULL) AS ma_sp,
            ten_sp,
            danh_muc
        FROM muahang.ton_kho_items
        WHERE ten_sp IS NOT NULL AND TRIM(ten_sp) <> ''
        GROUP BY 1, 2, 3
    """)).fetchall()

    prod_map: dict[tuple, int] = {}
    used_ma_sp: set[str] = set()
    # Preload existing ma_sp
    for (m,) in bind.execute(sa.text("SELECT ma_sp FROM ketoan.product")).fetchall():
        used_ma_sp.add(m)

    for ma_sp, ten_sp, danh_muc in sp_rows:
        cat_id = cat_map.get(danh_muc) if danh_muc else None
        cat_id = cat_id or default_cat_id

        # Determine ma_sp final
        if ma_sp:
            final_ma = ma_sp[:64]
        else:
            base = _slugify(ten_sp, "SP")[:60]
            final_ma = base
            i = 1
            while final_ma in used_ma_sp:
                i += 1
                suffix = f"-{i}"
                final_ma = (base[: 64 - len(suffix)] + suffix)
        used_ma_sp.add(final_ma)

        existing = bind.execute(sa.text(
            "SELECT id FROM ketoan.product WHERE ma_sp = :m"
        ), {"m": final_ma}).first()
        if existing:
            prod_map[(ma_sp, ten_sp, danh_muc)] = existing[0]
            continue
        result = bind.execute(sa.text("""
            INSERT INTO ketoan.product(
                ma_sp, ten_sp, category_id, dvt, attributes,
                gia_ban_mac_dinh, active
            )
            VALUES (
                :ma, :ten, :cat, 'cái', '{"backfilled":"muahang.ton_kho_items"}'::jsonb,
                0, TRUE
            )
            RETURNING id
        """), {"ma": final_ma, "ten": ten_sp, "cat": cat_id})
        prod_map[(ma_sp, ten_sp, danh_muc)] = result.scalar_one()

    # ─── 3. Mỗi ton_kho_items → 1 inventory_movement(loai='nhap') ──────────
    src_rows = bind.execute(sa.text("""
        SELECT
            id, COALESCE(NULLIF(TRIM(ma_sp), ''), NULL) AS ma_sp,
            ten_sp, danh_muc,
            COALESCE(ngay_nhap, created_at::date, CURRENT_DATE) AS ngay,
            COALESCE(so_luong, 0) AS sl,
            COALESCE(don_gia, 0) AS dg,
            COALESCE(thanh_tien, 0) AS tt,
            ghi_chu, nguoi_nhap
        FROM muahang.ton_kho_items
        ORDER BY COALESCE(ngay_nhap, created_at::date), id
    """)).fetchall()

    moved = 0
    for r in src_rows:
        sid, ma_sp, ten_sp, danh_muc, ngay, sl, dg, tt, ghi_chu, nguoi_nhap = r
        if sl is None or float(sl) <= 0:
            continue
        product_id = prod_map.get((ma_sp, ten_sp, danh_muc))
        if not product_id:
            continue
        doc_id = f"TKI-{sid}"
        # Idempotent
        exists = bind.execute(sa.text("""
            SELECT 1 FROM ketoan.inventory_movement
            WHERE source_app='muahang_tonkho' AND source_doc_id=:d
        """), {"d": doc_id}).first()
        if exists:
            continue
        bind.execute(sa.text("""
            INSERT INTO ketoan.inventory_movement(
                ngay, product_id, loai, so_luong, don_gia, thanh_tien,
                source_app, source_doc_id, ghi_chu, created_by
            )
            VALUES (
                :ngay, :pid, 'nhap', :sl, :dg, :tt,
                'muahang_tonkho', :doc, :gc, :by
            )
        """), {
            "ngay": ngay, "pid": product_id, "sl": sl, "dg": dg,
            "tt": tt if (tt and float(tt) > 0) else (float(sl) * float(dg)),
            "doc": doc_id, "gc": ghi_chu, "by": nguoi_nhap,
        })
        moved += 1

    # ─── 4. Recalc inventory_balance: replay chronological, bình quân ──────
    # Strategy: clear & rebuild for products đã có movements.
    bind.execute(sa.text("""
        DELETE FROM ketoan.inventory_balance
        WHERE product_id IN (
            SELECT DISTINCT product_id FROM ketoan.inventory_movement
        )
    """))
    # Per-product replay
    pids = [
        pid for (pid,) in bind.execute(sa.text(
            "SELECT DISTINCT product_id FROM ketoan.inventory_movement"
        )).fetchall()
    ]
    for pid in pids:
        rows = bind.execute(sa.text("""
            SELECT loai, so_luong, don_gia
            FROM ketoan.inventory_movement
            WHERE product_id=:p
            ORDER BY ngay, id
        """), {"p": pid}).fetchall()
        sl_ton = 0.0
        avg = 0.0
        for loai, sl, dg in rows:
            sl_f = float(sl or 0)
            dg_f = float(dg or 0)
            if loai == "nhap":
                new_qty = sl_ton + sl_f
                if new_qty > 0:
                    avg = (sl_ton * avg + sl_f * dg_f) / new_qty
                else:
                    avg = 0
                sl_ton = new_qty
            elif loai == "xuat":
                sl_ton -= sl_f
            elif loai == "dieu_chinh":
                sl_ton += sl_f
        bind.execute(sa.text("""
            INSERT INTO ketoan.inventory_balance(
                product_id, so_luong_ton, gia_von_bq, gia_tri_ton,
                ton_min, ton_max, last_updated
            )
            VALUES (:p, :sl, :avg, :gt, 0, 0, NOW())
        """), {"p": pid, "sl": sl_ton, "avg": avg, "gt": sl_ton * avg})


def downgrade() -> None:
    # Xoá inventory rows do backfill insert (source_app='muahang_tonkho')
    op.execute(
        "DELETE FROM ketoan.inventory_movement "
        "WHERE source_app='muahang_tonkho'"
    )
    # Recalc balance còn lại — đơn giản: clear hết, reset bằng query rebuild
    # khi user chạy lại upgrade. Ở downgrade chỉ delete movements.
    op.execute(
        "DELETE FROM ketoan.inventory_balance "
        "WHERE product_id NOT IN ("
        "  SELECT DISTINCT product_id FROM ketoan.inventory_movement"
        ")"
    )
    # Không xoá product/product_category vì user có thể đã edit thêm.
