"""Bridge endpoints — bắt cầu VanChuyen (saleadmin) → ChiPhiPhatSinh + SoQuy (ketoan).

Pull-based UX:
    GET  /api/vc/pending-accounting        → list VC đã giao/hoàn thành chưa được
                                             ghi entry vào ketoan
    POST /api/chi-phi/from-vc/{ma_vh}      → 1-click ghi chi phí VC + thu COD

Cross-app: lazy import `saleadmin.app.models.VanChuyen` — same DB, no HTTP.
Pattern theo `revenue_from_order.py` (Task #3).

Idempotent ở DB layer: partial UNIQUE WHERE ref_vc IS NOT NULL trên cả
chi_phi_phat_sinh.ref_vc + so_quy.ref_vc (migration 0004_chi_phi_ref_vc).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import ChiPhiPhatSinh, SoQuy
from ..services import (
    create_all_from_vc,
    VC_TRIGGER_STATUSES,
    VCAccountingError,
)
from ._deps import require_ketoan_user


# 2 router, đăng ký 2 prefix khác nhau trong main
pending_router = APIRouter()
create_router = APIRouter()
_AUTH = Depends(require_ketoan_user)


def _vc_to_dict(vc, *, has_chi_phi: bool, has_so_quy: bool) -> dict:
    """Snapshot VC + flag đã ghi kế toán hay chưa cho FE render."""
    return {
        "ma_vh": vc.ma_vh,
        "ma_don": vc.ma_don,
        "ten_kh": vc.ten_kh,
        "dia_chi": vc.dia_chi,
        "don_vi_vc": vc.don_vi_vc,
        "trang_thai": vc.trang_thai,
        "chi_phi_vc": str(vc.chi_phi_vc) if vc.chi_phi_vc is not None else "0",
        "tien_thu_ho": str(vc.tien_thu_ho) if vc.tien_thu_ho is not None else "0",
        "ngay_giao": vc.ngay_giao.isoformat() if vc.ngay_giao else None,
        "updated_at": vc.updated_at.isoformat() if vc.updated_at else None,
        # cho phép FE biết bên nào còn pending
        "has_chi_phi_entry": has_chi_phi,
        "has_so_quy_entry": has_so_quy,
        "needs_chi_phi": (vc.chi_phi_vc or Decimal("0")) > 0 and not has_chi_phi,
        "needs_so_quy": (vc.tien_thu_ho or Decimal("0")) > 0 and not has_so_quy,
    }


@pending_router.get("/pending-accounting")
def pending_accounting_vc(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """List VC saleadmin trang_thai ∈ ('da_giao','hoan_thanh') chưa được ghi
    đầy đủ entry vào ketoan.

    Filter: 1 VC vào pending list nếu (chi_phi_vc>0 + chưa có chi_phi_phat_sinh)
    HOẶC (tien_thu_ho>0 + chưa có so_quy entry).

    Cross-app read trên cùng DB qlpps_dev. UI Kế Toán hiện list này — kế toán
    click 'Ghi kế toán' → POST /api/chi-phi/from-vc/{ma_vh}.
    """
    from saleadmin.app.models import VanChuyen  # cross-app, lazy

    # Set of ma_vh đã có chi_phi/so_quy entry — 2 query gom
    chi_phi_refs = {
        r for (r,) in db.execute(
            select(ChiPhiPhatSinh.ref_vc).where(ChiPhiPhatSinh.ref_vc.isnot(None))
        )
    }
    so_quy_refs = {
        r for (r,) in db.execute(
            select(SoQuy.ref_vc).where(SoQuy.ref_vc.isnot(None))
        )
    }

    stmt = (
        select(VanChuyen)
        .where(VanChuyen.trang_thai.in_(VC_TRIGGER_STATUSES))
        .order_by(
            VanChuyen.updated_at.desc().nulls_last(),
            VanChuyen.id.desc(),
        )
    )

    items = []
    for vc in db.execute(stmt).scalars():
        has_chi_phi = vc.ma_vh in chi_phi_refs
        has_so_quy = vc.ma_vh in so_quy_refs
        needs_chi_phi = (vc.chi_phi_vc or Decimal("0")) > 0 and not has_chi_phi
        needs_so_quy = (vc.tien_thu_ho or Decimal("0")) > 0 and not has_so_quy
        if not (needs_chi_phi or needs_so_quy):
            continue
        items.append(_vc_to_dict(
            vc, has_chi_phi=has_chi_phi, has_so_quy=has_so_quy,
        ))
    return {"total": len(items), "items": items}


@create_router.post(
    "/from-vc/{ma_vh}",
    status_code=status.HTTP_201_CREATED,
)
def create_chi_phi_from_vc_endpoint(
    ma_vh: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """1-click: ghi chi phí VC + thu COD từ 1 lệnh saleadmin.vanchuyen.

    Idempotent: nếu đã có entry (chi_phi hoặc so_quy) → 409.
    Nếu VC chưa terminal → 400. Nếu ma_vh không tồn tại → 404.

    Auto-fill:
      - chi_phi_phat_sinh: loai="Vận chuyển", quy="Quỹ Công Ty",
                           so_tien=vc.chi_phi_vc, ngay=vc.ngay_giao
      - so_quy:            loai="thu", tai_khoan="Tiền Mặt",
                           so_tien=vc.tien_thu_ho, ngay=vc.ngay_giao
    """
    try:
        result = create_all_from_vc(
            db, ma_vh, created_by=user.username,
            require_terminal=True, commit=True,
        )
    except VCAccountingError as e:
        if e.code == "vc_not_found":
            raise HTTPException(status.HTTP_404_NOT_FOUND, e.message)
        if e.code == "duplicate":
            raise HTTPException(status.HTTP_409_CONFLICT, e.message)
        # not_terminal → 400
        raise HTTPException(status.HTTP_400_BAD_REQUEST, e.message)

    chi_phi = result["chi_phi"]
    so_quy = result["so_quy"]

    log_action(
        db, app="ketoan", action="create_chi_phi_from_vc",
        user=user, request=request,
        resource=f"vc:{ma_vh}",
        payload={
            "ma_vh": ma_vh,
            "chi_phi_id": chi_phi.id if chi_phi else None,
            "chi_phi_so_tien": str(chi_phi.so_tien) if chi_phi else None,
            "so_quy_id": so_quy.id if so_quy else None,
            "so_quy_so_tien": str(so_quy.so_tien) if so_quy else None,
            "created": result["created"],
            "skipped": result["skipped"],
        },
    )

    return {
        "ma_vh": ma_vh,
        "created": result["created"],
        "skipped": result["skipped"],
        "chi_phi": (
            {
                "id": chi_phi.id,
                "ngay": chi_phi.ngay.isoformat(),
                "so_tien": str(chi_phi.so_tien),
                "loai_chi_phi": chi_phi.loai_chi_phi,
                "mo_ta": chi_phi.mo_ta,
                "ref_vc": chi_phi.ref_vc,
            } if chi_phi else None
        ),
        "so_quy": (
            {
                "id": so_quy.id,
                "ngay": so_quy.ngay.isoformat(),
                "loai": so_quy.loai,
                "so_tien": str(so_quy.so_tien),
                "tai_khoan": so_quy.tai_khoan,
                "noi_dung": so_quy.noi_dung,
                "ref_vc": so_quy.ref_vc,
            } if so_quy else None
        ),
    }
