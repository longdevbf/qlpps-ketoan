"""BOM calculations — recalc tổng giá vốn + margin theo nhóm SP.

`recalc_bom_total(db, bom_id)` — SUM(items.thanh_tien) → bom_master.tong_gia_von
`get_active_bom_for_category(db, category_id, ngay)` — BOM active phù hợp ngày
`calc_margin_by_category(db, tu, den)` — so giá vốn BOM (lý thuyết)
    vs giá bán bình quân thực tế cho nhóm SP trong kỳ.

Quy ước Papasan:
  - BOM là tham khảo định giá (không phải xuất NVL khi sản xuất).
  - Margin "lý thuyết" = (gia_ban_bq - bom_gia_von) / gia_ban_bq * 100
  - Fail-soft: chưa có inventory_movement / doanh_thu → trả 0.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, or_, select, func
from sqlalchemy.orm import Session

from ..models import (
    BOMMaster, BOMItem,
    DoanhThu, InventoryMovement,
    InvProduct, InvProductCategory,
)


def next_ma_bom(db: Session) -> str:
    """Sinh mã BOM tiếp theo: BOM-001, BOM-002, ..."""
    rows = db.execute(
        select(BOMMaster.ma_bom).where(BOMMaster.ma_bom.like("BOM-%"))
    ).all()
    max_seq = 0
    for (ma,) in rows:
        try:
            seq = int(str(ma).split("-", 1)[1])
            if seq > max_seq:
                max_seq = seq
        except (ValueError, IndexError, TypeError):
            continue
    return f"BOM-{max_seq + 1:03d}"


def recalc_bom_total(db: Session, bom_id: int) -> Decimal:
    """Recalc tong_gia_von = SUM(items.thanh_tien). Trả về tổng mới.

    Caller chịu trách nhiệm flush/commit.
    """
    total = db.execute(
        select(func.coalesce(func.sum(BOMItem.thanh_tien), 0))
        .where(BOMItem.bom_id == bom_id)
    ).scalar() or Decimal("0")
    total = Decimal(str(total))
    bom = db.get(BOMMaster, bom_id)
    if bom:
        bom.tong_gia_von = total
        db.flush()
    return total


def get_active_bom_for_category(
    db: Session, category_id: int, ngay: Optional[date] = None,
) -> Optional[BOMMaster]:
    """Trả BOM active phù hợp ngày cho 1 nhóm SP.

    Tiêu chí:
      - active = TRUE
      - category_id khớp
      - effective_from <= ngay <= effective_to (NULL = vô hạn)
      - Nếu nhiều BOM thoả mãn → lấy bản có effective_from gần nhất (mới nhất).
    """
    if ngay is None:
        ngay = date.today()
    stmt = (
        select(BOMMaster)
        .where(
            BOMMaster.active.is_(True),
            BOMMaster.category_id == category_id,
            BOMMaster.effective_from <= ngay,
            or_(
                BOMMaster.effective_to.is_(None),
                BOMMaster.effective_to >= ngay,
            ),
        )
        .order_by(BOMMaster.effective_from.desc(), BOMMaster.id.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def calc_margin_by_category(
    db: Session, tu: date, den: date,
) -> list[dict]:
    """So giá vốn BOM vs giá bán bình quân thực tế (theo nhóm SP) trong kỳ.

    Logic:
      1. Mỗi nhóm SP có BOM active trong kỳ → bom_gia_von.
      2. Tính tổng SL xuất (loai='xuat') trong kỳ cho SP thuộc nhóm.
      3. Doanh thu thực: SUM(doanh_thu.so_tien) trong kỳ — Papasan ghi
         doanh thu theo PO không gắn product_id, nên phân bổ pro-rata
         theo SL xuất của nhóm trên tổng SL xuất tất cả nhóm.
      4. gia_ban_bq = doanh_thu_phan_bo / so_luong_xuat
      5. margin_pct = (gia_ban_bq - bom_gia_von) / gia_ban_bq * 100

    Fail-soft: chưa có data → 0.
    """
    # ─── 1. Lấy BOM active per category trong kỳ ──────────────────────────
    # BOM active "trong kỳ" = effective_from <= den AND (effective_to IS NULL OR effective_to >= tu)
    bom_stmt = (
        select(BOMMaster, InvProductCategory)
        .join(
            InvProductCategory,
            BOMMaster.category_id == InvProductCategory.id,
            isouter=True,
        )
        .where(
            BOMMaster.active.is_(True),
            BOMMaster.category_id.is_not(None),
            BOMMaster.effective_from <= den,
            or_(
                BOMMaster.effective_to.is_(None),
                BOMMaster.effective_to >= tu,
            ),
        )
        .order_by(
            BOMMaster.category_id,
            BOMMaster.effective_from.desc(),
            BOMMaster.id.desc(),
        )
    )
    rows = db.execute(bom_stmt).all()
    seen: set[int] = set()
    boms_by_cat: dict[int, tuple[BOMMaster, Optional[InvProductCategory]]] = {}
    for bom, cat in rows:
        if bom.category_id in seen:
            continue
        seen.add(bom.category_id)
        boms_by_cat[bom.category_id] = (bom, cat)
    if not boms_by_cat:
        return []

    # ─── 2. Tổng SL xuất per category trong kỳ ────────────────────────────
    sl_stmt = (
        select(
            InvProduct.category_id,
            func.coalesce(func.sum(InventoryMovement.so_luong), 0),
        )
        .join(InvProduct, InvProduct.id == InventoryMovement.product_id)
        .where(
            InventoryMovement.loai == "xuat",
            InventoryMovement.ngay >= tu,
            InventoryMovement.ngay <= den,
        )
        .group_by(InvProduct.category_id)
    )
    sl_by_cat: dict[int, Decimal] = {
        int(cid): Decimal(str(sl)) for cid, sl in db.execute(sl_stmt).all()
    }
    total_sl = sum(sl_by_cat.values(), Decimal("0"))

    # ─── 3. Tổng doanh thu trong kỳ (chưa phân bổ theo SP) ────────────────
    # Papasan: doanh_thu không gắn product_id → phân bổ pro-rata theo SL xuất.
    total_dt = db.execute(
        select(func.coalesce(func.sum(DoanhThu.so_tien), 0))
        .where(DoanhThu.ngay >= tu, DoanhThu.ngay <= den)
    ).scalar() or 0
    total_dt = Decimal(str(total_dt))

    # ─── 4. Tổng hợp ──────────────────────────────────────────────────────
    out: list[dict] = []
    for cat_id, (bom, cat) in boms_by_cat.items():
        sl = sl_by_cat.get(cat_id, Decimal("0"))
        # Phân bổ doanh thu pro-rata theo SL xuất của nhóm
        if total_sl > 0 and sl > 0:
            dt_phan_bo = (total_dt * sl / total_sl).quantize(Decimal("0.01"))
            gia_ban_bq = (dt_phan_bo / sl).quantize(Decimal("0.01"))
        else:
            dt_phan_bo = Decimal("0")
            gia_ban_bq = Decimal("0")

        bom_gia_von = Decimal(str(bom.tong_gia_von or 0))
        margin_pct: Optional[Decimal] = None
        if gia_ban_bq > 0:
            margin_pct = (
                (gia_ban_bq - bom_gia_von) / gia_ban_bq * Decimal("100")
            ).quantize(Decimal("0.01"))

        out.append({
            "category_id": cat_id,
            "ma_nhom": cat.ma_nhom if cat else None,
            "ten_nhom": cat.ten_nhom if cat else f"#{cat_id}",
            "bom_id": bom.id,
            "ma_bom": bom.ma_bom,
            "bom_gia_von": bom_gia_von,
            "gia_ban_bq": gia_ban_bq,
            "margin_pct": margin_pct,
            "so_luong_xuat": sl,
            "doanh_thu_thuc": dt_phan_bo,
        })
    out.sort(key=lambda x: x["ten_nhom"])
    return out
