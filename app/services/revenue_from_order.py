"""Helper service — tạo DoanhThu entry từ 1 PurchaseOrder của muahang.

Phase 4 (2026-04-28) Revenue Recognition refactor:
  ─ DT/COGS giờ được sinh khi VC `hoan_thanh` (kế toán đối chiếu xong),
    KHÔNG phải khi PO `Đã giao` hay `Hoàn Thành`.
  ─ Auto-trigger từ muahang đã bị DISABLED (xem `create_doanh_thu_from_order`).
  ─ Endpoint manual `POST /api/doanh-thu/from-order/{order_id}` vẫn hoạt động
    (kế toán có thể click thủ công nếu cần — vd dòng cũ chưa có VC).

Giữ logic ở 1 chỗ để có thể gọi từ:
    - Endpoint manual `POST /api/doanh-thu/from-order/{order_id}` (require_terminal=True)
    - [DISABLED] Trigger tự động từ muahang `_auto_bridge_to_ketoan` (require_terminal=False)
      → giờ raise RevenueFromOrderError(code='auto_disabled') để no-op fail-soft.

Cross-app: dùng SQLAlchemy session đang sống cùng DB (qlpps_dev) — KHÔNG HTTP call.
Lazy import models của muahang/baogia trong function body để tránh circular.
"""
from __future__ import annotations

from datetime import date as date_cls
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DoanhThu


# Set status "trigger" doanh thu — định nghĩa 1 nơi
REVENUE_TRIGGER_STATUSES = {"Đã giao", "Hoàn Thành"}


class RevenueFromOrderError(Exception):
    """Raise khi không thể tạo doanh thu từ PO (PO chưa terminal, PO không có)."""

    def __init__(self, code: str, message: str):
        self.code = code  # 'po_not_found' | 'po_not_terminal' | 'duplicate'
        self.message = message
        super().__init__(message)


def _lookup_quote_total(db: Session, ref_bao_gia: Optional[str]):
    """Trả (tong_don, customer_name, salesperson) từ baogia.quotes — fail-soft."""
    if not ref_bao_gia:
        return None, None, None
    from baogia.app.models import Quote  # lazy cross-app
    q = db.execute(
        select(Quote).where(Quote.quote_number == ref_bao_gia)
    ).scalar_one_or_none()
    if not q:
        return None, None, None
    return q.tong_don, q.customer_name, q.salesperson


def find_existing_doanh_thu_for_order(db: Session, order_id: str) -> Optional[DoanhThu]:
    """Trả DoanhThu nếu đã có entry cho PO này, else None."""
    return db.execute(
        select(DoanhThu).where(DoanhThu.ref_order_id == order_id)
    ).scalar_one_or_none()


def create_doanh_thu_from_order(
    db: Session,
    order_id: str,
    *,
    created_by: Optional[str] = None,
    require_terminal: bool = True,
    commit: bool = True,
) -> DoanhThu:
    """Tạo entry DoanhThu cho 1 PO. Idempotent — raise duplicate nếu đã có.

    Args:
        db: SQLAlchemy session (bound vào qlpps_dev — multi-schema).
        order_id: 'ORD-2026-XXX'
        created_by: username người tạo (audit).
        require_terminal: nếu True, từ chối khi PO chưa ở status terminal
            (Đã giao / Hoàn Thành). Trigger nội bộ có thể bypass = False.
        commit: nếu False, caller tự commit (dùng khi gọi trong cùng tx).

    Raises:
        RevenueFromOrderError(code='po_not_found' | 'po_not_terminal' | 'duplicate'
                              | 'auto_disabled')
    """
    # ─── Phase 4 Revenue Recognition (2026-04-28) ──────────────────────────────
    # Auto-trigger từ muahang `_auto_bridge_to_ketoan` truyền `require_terminal=False`.
    # Logic mới: DT/COGS được sinh khi kế toán đối chiếu VC `hoan_thanh` (xem
    # `routers/external.py:mark_vanchuyen_completed`). Vì thế ở đây chặn auto-trigger
    # để tránh ghi DT trùng / quá sớm. Manual call (require_terminal=True) vẫn OK.
    if not require_terminal:
        raise RevenueFromOrderError(
            "auto_disabled",
            "Auto bridge muahang→DoanhThu đã DISABLED (Phase 4 Rev Rec). "
            "DT/COGS giờ sinh khi VC `hoan_thanh`. Endpoint manual vẫn hoạt động."
        )

    from muahang.app.models import PurchaseOrder  # lazy cross-app

    po = db.get(PurchaseOrder, order_id)
    if not po:
        raise RevenueFromOrderError("po_not_found", f"Không tìm thấy đơn {order_id}")

    if require_terminal and po.status not in REVENUE_TRIGGER_STATUSES:
        raise RevenueFromOrderError(
            "po_not_terminal",
            f"Đơn {order_id} đang ở trạng thái '{po.status}' — chưa thể ghi doanh thu "
            f"(cần status ∈ {sorted(REVENUE_TRIGGER_STATUSES)})",
        )

    existing = find_existing_doanh_thu_for_order(db, order_id)
    if existing:
        raise RevenueFromOrderError(
            "duplicate",
            f"Đơn {order_id} đã có entry doanh thu (id={existing.id})",
        )

    tong_don, customer_name, salesperson = _lookup_quote_total(db, po.ref_bao_gia)
    so_tien = tong_don if tong_don is not None else Decimal("0")

    ngay = (po.updated_at.date() if po.updated_at else None) or date_cls.today()

    ghi_chu_parts = [f"Doanh thu đơn {order_id}"]
    if po.ref_bao_gia:
        ghi_chu_parts.append(f"BG: {po.ref_bao_gia}")
    if customer_name:
        ghi_chu_parts.append(f"KH: {customer_name}")
    ghi_chu = " — ".join(ghi_chu_parts)

    obj = DoanhThu(
        ngay=ngay,
        loai="Doanh Số Đồ Gỗ Lẻ",
        so_tien=so_tien,
        nguon="kd",
        nv_kinh_doanh=salesperson,
        ma_don=po.ref_bao_gia,
        ref_order_id=order_id,
        loai_thanh_toan="Thanh Toán",
        mo_ta=po.ten_don,
        ghi_chu=ghi_chu,
        created_by=created_by,
    )
    db.add(obj)
    if commit:
        db.commit()
        db.refresh(obj)
    else:
        db.flush()
    return obj
