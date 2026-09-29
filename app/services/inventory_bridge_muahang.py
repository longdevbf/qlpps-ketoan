"""Bridge muahang.PurchaseOrder → ketoan inventory (NHẬP KHO).

Khi PO chuyển sang status terminal (Đã giao / Hoàn Thành), tự động:
  - Map mỗi POItem → InvProduct (qua ma_sp; auto-create nếu chưa có,
    category mặc định 'Khác' hoặc lấy từ POItem.ma_don/ten_sp).
  - Tạo InventoryMovement(loai='nhap') với don_gia = giá NCC selected.
  - Recalc InventoryBalance qua `inventory_avg.apply_movement`.

Idempotent: dùng (source_app='muahang', source_doc_id=PO.id+'-'+item.id) để
detect đã ghi rồi. Fail-soft — exceptions chỉ log, không raise lên flow PO.
"""
from __future__ import annotations

import logging
from datetime import date as date_cls
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from .ma_san_pham import ma_kieu_cu, ma_moi_cho
from sqlalchemy.orm import Session

from ..models import (
    InvProduct, InvProductCategory, InventoryMovement,
)
from .inventory_avg import apply_movement, get_or_create_balance


logger = logging.getLogger(__name__)


PO_TRIGGER_STATUSES = {"Đã giao", "Hoàn Thành", "da_giao_hang"}
DEFAULT_CATEGORY_MA = "KHAC"
DEFAULT_CATEGORY_TEN = "Khác (auto)"


def _ensure_default_category(db: Session) -> InvProductCategory:
    cat = db.execute(
        select(InvProductCategory).where(InvProductCategory.ma_nhom == DEFAULT_CATEGORY_MA)
    ).scalar_one_or_none()
    if cat:
        return cat
    cat = InvProductCategory(
        ma_nhom=DEFAULT_CATEGORY_MA,
        ten_nhom=DEFAULT_CATEGORY_TEN,
        parent_id=None,
        display_order=999,
        active=True,
    )
    db.add(cat)
    db.flush()
    return cat


def _resolve_or_create_product(
    db: Session,
    *,
    ma_sp: Optional[str],
    ten_sp: str,
    dvt: Optional[str],
) -> InvProduct:
    """Tìm InvProduct theo ma_sp; nếu không có và có ma_sp → tạo mới.
    Nếu ma_sp rỗng → slug từ ten_sp.
    """
    if ma_sp:
        p = db.execute(
            select(InvProduct).where(InvProduct.ma_sp == ma_sp)
        ).scalar_one_or_none()
        if p:
            return p
    # Mã tự sinh: không dấu, viết hoa, nối "_" như danh mục chung (28/09/2026) — ưu tiên mã shared.products cùng tên.
    candidate_ma = (ma_sp or ma_moi_cho(db, ten_sp) or f"SP_{int(date_cls.today().toordinal())}")[:64]
    # Sản phẩm đã có: theo mã mới, hoặc theo mã tự sinh kiểu cũ (còn dấu, nối "-") nếu chưa chạy chuẩn hoá mã.
    for ma_tim in {candidate_ma, ma_kieu_cu(ten_sp)} - {""}:
        p = db.execute(
            select(InvProduct).where(InvProduct.ma_sp == ma_tim)
        ).scalar_one_or_none()
        if p:
            return p

    cat = _ensure_default_category(db)
    p = InvProduct(
        ma_sp=candidate_ma,
        ten_sp=ten_sp or candidate_ma,
        category_id=cat.id,
        dvt=dvt or "cái",
        attributes={"auto_created_from": "muahang"},
        gia_ban_mac_dinh=Decimal("0"),
        active=True,
    )
    db.add(p)
    db.flush()
    return p


def _movement_exists(db: Session, source_doc_id: str) -> bool:
    return db.execute(
        select(InventoryMovement.id).where(
            InventoryMovement.source_app == "muahang",
            InventoryMovement.source_doc_id == source_doc_id,
        )
    ).first() is not None


def on_po_delivered(db: Session, po, *, created_by: Optional[str] = None) -> dict:
    """Hook chính — gọi sau khi PO commit status terminal.

    Args:
        db: SA session.
        po: PurchaseOrder ORM (đã loaded items + selected_ncc_id).
        created_by: username audit.

    Returns:
        {'po_id': str, 'movements_created': int, 'skipped': int, 'errors': [str,...]}

    Fail-soft: bắt mọi Exception trong from-loop, log + thêm vào errors.
    Caller có thể commit hoặc rollback tuỳ ý — service sẽ commit ở cuối nếu OK.
    """
    result = {
        "po_id": getattr(po, "id", None),
        "movements_created": 0,
        "skipped": 0,
        "errors": [],
    }
    try:
        items = list(getattr(po, "items", None) or [])
        if not items:
            return result

        # Resolve ngay nhập = ngay_dat_xuong > created_at > today
        ngay = getattr(po, "ngay_dat_xuong", None)
        if ngay is None:
            ca = getattr(po, "created_at", None)
            ngay = ca.date() if ca else date_cls.today()

        # Resolve don_gia per item from prices[selected_ncc_id]['don_gia']
        sel_ncc = getattr(po, "selected_ncc_id", None) or getattr(po, "comparison_best_ncc", None)

        for it in items:
            try:
                doc_id = f"{po.id}-{it.id}"
                if _movement_exists(db, doc_id):
                    result["skipped"] += 1
                    continue

                ten_sp = (it.ten_sp or "").strip() or f"item-{it.id}"
                ma_sp = None
                # POItem không có ma_sp riêng — derive từ ma_don nếu có (V1 convention)
                if getattr(it, "ma_don", None):
                    ma_sp = str(it.ma_don)[:64]

                product = _resolve_or_create_product(
                    db, ma_sp=ma_sp, ten_sp=ten_sp, dvt=getattr(it, "dvt", None),
                )

                # Số lượng từ so_luong_calc (parsed) > so_luong_input (raw)
                sl = it.so_luong_calc if getattr(it, "so_luong_calc", None) else None
                if sl is None:
                    try:
                        sl = Decimal(str(it.so_luong_input or "0").replace(",", "."))
                    except Exception:
                        sl = Decimal("0")
                sl = Decimal(sl or 0)
                if sl <= 0:
                    result["skipped"] += 1
                    continue

                # Đơn giá từ prices[selected_ncc]['don_gia']
                dg = Decimal("0")
                prices = getattr(it, "prices", None) or {}
                if sel_ncc and isinstance(prices.get(sel_ncc), dict):
                    raw = prices[sel_ncc].get("don_gia") or prices[sel_ncc].get("gia") or 0
                    try:
                        dg = Decimal(str(raw))
                    except Exception:
                        dg = Decimal("0")
                if dg <= 0 and prices:
                    # fallback: lấy NCC đầu tiên có don_gia
                    for _, p in prices.items():
                        if isinstance(p, dict):
                            raw = p.get("don_gia") or p.get("gia") or 0
                            try:
                                dg = Decimal(str(raw))
                                if dg > 0:
                                    break
                            except Exception:
                                pass

                m = InventoryMovement(
                    ngay=ngay,
                    product_id=product.id,
                    loai="nhap",
                    so_luong=sl,
                    don_gia=dg,
                    thanh_tien=sl * dg,
                    source_app="muahang",
                    source_doc_id=doc_id,
                    ghi_chu=f"Auto từ PO {po.id} ({(po.ten_don or '')[:120]})".strip(),
                    created_by=created_by,
                )
                db.add(m)
                db.flush()
                apply_movement(db, m)
                result["movements_created"] += 1
            except Exception as e:  # noqa: BLE001 — fail-soft per item
                logger.warning(
                    "inventory_bridge_muahang item failed po=%s item=%s err=%s",
                    po.id, getattr(it, "id", "?"), e,
                )
                result["errors"].append(f"{getattr(it, 'id', '?')}: {e}")

        db.commit()
    except Exception as e:  # noqa: BLE001 — top-level fail-soft
        logger.error("inventory_bridge_muahang failed po=%s: %s", getattr(po, "id", "?"), e)
        try:
            db.rollback()
        except Exception:
            pass
        result["errors"].append(str(e))
    return result
