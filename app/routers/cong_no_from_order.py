"""Bridge endpoints — bắt cầu PO (muahang) → CongNo phai_tra (ketoan).

Pull-based UX (đồng bộ pattern revenue_from_order):
    GET  /api/cong-no/pending-payable          → list PO đã giao/hoàn thành chưa ghi công nợ
    POST /api/cong-no/from-order/{order_id}    → 1-click ghi công nợ (idempotent)

Cross-app: lazy import muahang/baogia models — same DB, no HTTP.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import CongNo
from ..schemas import CongNoOut
from ..services import (
    create_cong_no_phai_tra_from_order,
    create_cong_no_list_from_order,
    PAYABLE_TRIGGER_STATUSES,
    CongNoFromOrderError,
)
from ._deps import require_ketoan_user


pending_router = APIRouter()
create_router = APIRouter()
_AUTH = Depends(require_ketoan_user)


@pending_router.get("/pending-payable")
def pending_payable_orders(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """List PO terminal chưa có CongNo phải trả.

    Trả `{total, items}`. Items có `ma_don, ten_don, ncc_name, so_tien_du_kien`
    (lookup từ ncc_totals + selected_ncc_id) để FE có thể hiển thị ngay.
    """
    from muahang.app.models import PurchaseOrder, Supplier  # lazy cross-app

    # Tập order_id ĐÃ ghi công nợ — derive từ ref_id (match cả 2 format:
    # cũ 'MH-{order}' và mới 'MH-{order}-NCC{ncc}'). Trước đây check
    # f"MH-{p.id}" in have_refs nên đơn format mới không bao giờ khớp →
    # đơn đã ghi vẫn hiện "chờ ghi" (bug 2026-06-19).
    recorded_orders: set[str] = set()
    for (r,) in db.execute(select(CongNo.ref_id).where(CongNo.ref_id.like("MH-%"))):
        if not r:
            continue
        oid = r[3:]  # bỏ tiền tố "MH-"
        idx = oid.find("-NCC")
        if idx != -1:
            oid = oid[:idx]
        recorded_orders.add(oid)

    stmt = (
        select(PurchaseOrder)
        .where(PurchaseOrder.status.in_(PAYABLE_TRIGGER_STATUSES))
        .order_by(PurchaseOrder.updated_at.desc().nulls_last(), PurchaseOrder.id.desc())
    )

    pos = list(db.execute(stmt).scalars())
    pending = [p for p in pos if p.id not in recorded_orders]

    suppliers = db.execute(select(Supplier.id, Supplier.name)).all()
    ncc_name_by_id = {s.id: s.name for s in suppliers}

    items = []
    for p in pending:
        totals = p.ncc_totals or {}
        names = p.ncc_names or {}
        sel_id = p.selected_ncc_id or p.comparison_best_ncc

        so_tien = None
        ncc_name = None
        if sel_id and str(sel_id) in totals:
            so_tien = str(totals[str(sel_id)])
            ncc_name = (
                names.get(str(sel_id))
                or ncc_name_by_id.get(sel_id)
                or str(sel_id)
            )
        elif totals:
            first_id = next(iter(totals.keys()))
            so_tien = str(totals[first_id])
            ncc_name = (
                names.get(first_id)
                or ncc_name_by_id.get(first_id)
                or first_id
            )

        items.append({
            "ma_don": p.id,
            "ten_don": p.ten_don,
            "status": p.status,
            "ncc_name": ncc_name,
            "so_tien_du_kien": so_tien,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        })
    return {"total": len(items), "items": items}


@create_router.post(
    "/from-order/{order_id}",
    status_code=status.HTTP_201_CREATED,
)
def create_cong_no_from_order_endpoint(
    order_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """1-click: tạo CongNo phai_tra per-NCC từ 1 PO của muahang.

    Tạo 1 entry riêng cho mỗi NCC trong ncc_totals.
    Idempotent: NCC đã có → skip. Tất cả đã có → 409.
    """
    try:
        objs = create_cong_no_list_from_order(
            db, order_id, created_by=user.username,
            require_terminal=True, commit=True,
        )
    except CongNoFromOrderError as e:
        if e.code == "po_not_found":
            raise HTTPException(status.HTTP_404_NOT_FOUND, e.message)
        if e.code == "duplicate":
            raise HTTPException(status.HTTP_409_CONFLICT, e.message)
        if e.code == "no_total":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, e.message)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, e.message)

    log_action(
        db, app="ketoan", action="create_cong_no_from_order",
        user=user, request=request,
        resource=",".join(f"cong_no:{o.id}" for o in objs),
        payload={
            "order_id": order_id,
            "created": [{"id": o.id, "doi_tac": o.doi_tac, "so_tien": str(o.so_tien)} for o in objs],
        },
    )
    return {"ok": True, "created": len(objs), "ids": [o.id for o in objs]}
