"""Bridge endpoints — bắt cầu PO (muahang) → DoanhThu (ketoan).

Pull-based UX:
    GET  /api/orders/pending-revenue           → list PO đã giao/hoàn thành chưa ghi DT
    POST /api/doanh-thu/from-order/{order_id}  → 1-click ghi DT (idempotent)

Cross-app: lazy import `muahang.app.models` + `baogia.app.models` — same DB,
no HTTP. Tuân constraint Tier 1.3 (Task #3).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import DoanhThu
from ..schemas import DoanhThuOut
from ..services import (
    create_doanh_thu_from_order,
    REVENUE_TRIGGER_STATUSES,
    RevenueFromOrderError,
)
from ._deps import require_ketoan_user


# Một router cho 2 prefix khác nhau — đăng ký 2 lần với tag riêng trong main.
pending_router = APIRouter()
create_router = APIRouter()
_AUTH = Depends(require_ketoan_user)


@pending_router.get("/pending-revenue")
def pending_revenue_orders(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """List PO của muahang status ∈ ('Đã giao', 'Hoàn Thành') chưa có DoanhThu entry.

    Cross-app read trên cùng DB qlpps_dev. UI Kế Toán hiện list này — kế toán click
    'Ghi doanh thu' → POST /api/doanh-thu/from-order/{id}.

    Pattern tham khảo: muahang.routers.orders.pending_quotes_from_baogia.
    """
    from muahang.app.models import PurchaseOrder  # cross-app, lazy
    from baogia.app.models import Quote            # cross-app, lazy

    have_refs = {
        r for (r,) in db.execute(
            select(DoanhThu.ref_order_id).where(DoanhThu.ref_order_id.isnot(None))
        )
    }

    stmt = (
        select(PurchaseOrder)
        .where(PurchaseOrder.status.in_(REVENUE_TRIGGER_STATUSES))
        .order_by(PurchaseOrder.updated_at.desc().nulls_last(), PurchaseOrder.id.desc())
    )

    # Build customer_name map từ baogia.quotes (1 query gom)
    pos = list(db.execute(stmt).scalars())
    pending = [p for p in pos if p.id not in have_refs]
    refs = {p.ref_bao_gia for p in pending if p.ref_bao_gia}
    cust_map: dict[str, dict] = {}
    if refs:
        for q in db.execute(
            select(Quote).where(Quote.quote_number.in_(refs))
        ).scalars():
            cust_map[q.quote_number] = {
                "customer_name": q.customer_name,
                "tong_don": str(q.tong_don) if q.tong_don is not None else None,
                "salesperson": q.salesperson,
            }

    items = []
    for p in pending:
        meta = cust_map.get(p.ref_bao_gia or "", {})
        items.append({
            "ma_don": p.id,
            "ten_don": p.ten_don,
            "ref_bao_gia": p.ref_bao_gia,
            "status": p.status,
            "customer_name": meta.get("customer_name"),
            "tong_don": meta.get("tong_don"),
            "salesperson": meta.get("salesperson"),
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        })
    return {"total": len(items), "items": items}


@create_router.post(
    "/from-order/{order_id}",
    response_model=DoanhThuOut,
    status_code=status.HTTP_201_CREATED,
)
def create_doanh_thu_from_order_endpoint(
    order_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """1-click: tạo DoanhThu từ 1 PO của muahang.

    Idempotent: nếu PO đã có entry → 409. Nếu PO chưa giao → 400.
    Auto fill so_tien từ baogia.quotes.tong_don (qua ref_bao_gia).
    """
    try:
        obj = create_doanh_thu_from_order(
            db, order_id, created_by=user.username,
            require_terminal=True, commit=True,
        )
    except RevenueFromOrderError as e:
        if e.code == "po_not_found":
            raise HTTPException(status.HTTP_404_NOT_FOUND, e.message)
        if e.code == "duplicate":
            raise HTTPException(status.HTTP_409_CONFLICT, e.message)
        # po_not_terminal → 400
        raise HTTPException(status.HTTP_400_BAD_REQUEST, e.message)

    log_action(
        db, app="ketoan", action="create_doanh_thu_from_order",
        user=user, request=request,
        resource=f"doanh_thu:{obj.id}",
        payload={
            "ref_order_id": order_id,
            "so_tien": str(obj.so_tien),
            "ngay": str(obj.ngay),
            "ma_don": obj.ma_don,
        },
    )
    return obj
