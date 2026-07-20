"""Bridge saleadmin.VanChuyen → ketoan inventory (XUẤT KHO).

[Phase 4 Revenue Recognition — 2026-04-28] DISABLED.
─────────────────────────────────────────────────────────────────────────────
Logic xuất kho đã được di chuyển vào `routers/external.py:mark_vanchuyen_completed`
(`_deduct_inventory_fifo`) — trừ tồn FIFO trên `muahang.ton_kho_items` khi VC
`hoan_thanh` (kế toán đối chiếu thu/chi xong). Bridge cũ này (xuất kho khi
VC `da_giao`) đã bị no-op để:
  - Tránh double-count xuất kho.
  - Đảm bảo ghi nhận COGS đúng timing (chỉ khi đã đối chiếu).

`on_vc_delivered()` giờ trả no-op result. Function được giữ lại để các caller
hiện tại (saleadmin/app/routers/vanchuyen.py) không vỡ — không xoá file.
─────────────────────────────────────────────────────────────────────────────

(Logic CŨ — đã vô hiệu hoá):
  Khi VC chuyển sang trang_thai='da_giao' (hoặc 'hoan_thanh'), tự động:
    - Tra ngược tới PO qua vc.ma_don → lấy items.
    - Mỗi item → InventoryMovement(loai='xuat'), don_gia auto = current avg.
    - Update InventoryBalance qua `inventory_avg.apply_movement`.

  Idempotent: source_app='saleadmin', source_doc_id=ma_vh+'-'+item_id.
  Fail-soft — exceptions log only.
"""
from __future__ import annotations

import logging
from datetime import date as date_cls
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import InvProduct, InventoryMovement
from .inventory_avg import apply_movement
from .inventory_bridge_muahang import _resolve_or_create_product


logger = logging.getLogger(__name__)


VC_TRIGGER_STATUSES = {"da_giao", "hoan_thanh", "Đã giao", "Hoàn thành"}


def _movement_exists(db: Session, source_doc_id: str) -> bool:
    return db.execute(
        select(InventoryMovement.id).where(
            InventoryMovement.source_app == "saleadmin",
            InventoryMovement.source_doc_id == source_doc_id,
        )
    ).first() is not None


def _resolve_po_items(db: Session, ma_don: Optional[str]):
    """Trả list POItem qua ma_don. Lazy import muahang."""
    if not ma_don:
        return []
    try:
        from muahang.app.models import PurchaseOrder
        po = db.get(PurchaseOrder, ma_don)
        return list(po.items) if po else []
    except Exception as e:  # noqa: BLE001
        logger.warning("inventory_bridge_saleadmin: cannot load PO %s: %s", ma_don, e)
        return []


def on_vc_delivered(db: Session, vc, *, created_by: Optional[str] = None) -> dict:
    """[DISABLED — Phase 4 Rev Rec, 2026-04-28] Bridge xuất kho khi VC `da_giao`.

    No-op. Logic xuất kho đã chuyển vào
    `ketoan/app/routers/external.py:mark_vanchuyen_completed` — trừ tồn FIFO
    trên `muahang.ton_kho_items` khi VC `hoan_thanh` (kế toán đối chiếu).
    Function này được giữ lại để các caller cũ (vd
    `saleadmin/app/routers/vanchuyen.py:_bridge_inventory_safe`) không vỡ.

    Returns no-op shape (movements_created=0, skipped=0, disabled=True).
    """
    return {
        "ma_vh": getattr(vc, "ma_vh", None),
        "movements_created": 0,
        "skipped": 0,
        "errors": [],
        "disabled": True,
        "note": "Phase 4 Rev Rec: logic moved to mark_vanchuyen_completed (FIFO).",
    }


def _on_vc_delivered_legacy(db: Session, vc, *, created_by: Optional[str] = None) -> dict:
    """[LEGACY — DEAD CODE] Logic cũ xuất kho khi VC `da_giao`.

    Giữ lại để tham khảo / có thể migrate dữ liệu cũ. KHÔNG GỌI từ caller mới.
    """
    result = {
        "ma_vh": getattr(vc, "ma_vh", None),
        "movements_created": 0,
        "skipped": 0,
        "errors": [],
    }
    try:
        items = _resolve_po_items(db, getattr(vc, "ma_don", None))
        if not items:
            return result

        ngay = getattr(vc, "ngay_giao", None) or date_cls.today()

        for it in items:
            try:
                doc_id = f"{vc.ma_vh}-{it.id}"
                if _movement_exists(db, doc_id):
                    result["skipped"] += 1
                    continue

                ten_sp = (it.ten_sp or "").strip() or f"item-{it.id}"
                ma_sp = None
                if getattr(it, "ma_don", None):
                    ma_sp = str(it.ma_don)[:64]
                product = _resolve_or_create_product(
                    db, ma_sp=ma_sp, ten_sp=ten_sp, dvt=getattr(it, "dvt", None),
                )

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

                m = InventoryMovement(
                    ngay=ngay,
                    product_id=product.id,
                    loai="xuat",
                    so_luong=sl,
                    don_gia=Decimal("0"),
                    thanh_tien=Decimal("0"),
                    source_app="saleadmin",
                    source_doc_id=doc_id,
                    ghi_chu=f"Auto xuất kho từ VC {vc.ma_vh} (đơn {vc.ma_don})",
                    created_by=created_by,
                )
                db.add(m)
                db.flush()
                apply_movement(db, m, allow_negative=True)
                result["movements_created"] += 1
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "inventory_bridge_saleadmin item failed vc=%s item=%s err=%s",
                    vc.ma_vh, getattr(it, "id", "?"), e,
                )
                result["errors"].append(f"{getattr(it, 'id', '?')}: {e}")

        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.error("inventory_bridge_saleadmin failed vc=%s: %s",
                     getattr(vc, "ma_vh", "?"), e)
        try:
            db.rollback()
        except Exception:
            pass
        result["errors"].append(str(e))
    return result
