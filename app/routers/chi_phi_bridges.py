"""Bridge endpoints — auto-tạo ChiPhi từ marketing (ADS) + hcns (Lương).

Mounted dưới /api/chi-phi prefix:
    POST /api/chi-phi/from-ads/{thang}      — sync ADS marketing tháng X
    POST /api/chi-phi/from-payroll/{thang}  — sync lương HCNS tháng X
    GET  /api/chi-phi/from-ads/{thang}      — preview (chưa commit)
    GET  /api/chi-phi/from-payroll/{thang}  — preview (chưa commit)
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ._deps import require_ketoan_user
from ..services.chi_phi_from_ads import sync_chi_phi_from_ads
from ..services.chi_phi_from_payroll import sync_chi_phi_from_payroll


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


def _can_write(user: JWTPayload) -> bool:
    return user.role in ("admin", "ceo", "assistant_ceo", "manager")


@router.post("/from-ads/{thang}")
def post_chi_phi_from_ads(
    thang: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
) -> dict:
    """Sync chi phí ADS marketing tháng X. Idempotent — gọi lại sẽ UPDATE."""
    if not _can_write(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ admin/manager được sync")
    if len(thang) != 7 or thang[4] != "-":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "thang format YYYY-MM")

    result = sync_chi_phi_from_ads(db, thang, nguoi_chi=user.username or "auto-bridge")
    log_action(
        db, app="ketoan", action="bridge_chi_phi_from_ads", user=user, request=request,
        resource=f"chi_phi:ads:{thang}",
        payload={"upserted": result.get("upserted"), "total": result.get("total_amount")},
    )
    return result


@router.post("/from-payroll/{thang}")
def post_chi_phi_from_payroll(
    thang: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
) -> dict:
    """Sync chi phí lương HCNS tháng X — gộp 1 row/phòng ban."""
    if not _can_write(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ admin/manager được sync")
    if len(thang) != 7 or thang[4] != "-":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "thang format YYYY-MM")

    result = sync_chi_phi_from_payroll(db, thang, nguoi_chi=user.username or "auto-bridge")
    log_action(
        db, app="ketoan", action="bridge_chi_phi_from_payroll", user=user, request=request,
        resource=f"chi_phi:payroll:{thang}",
        payload={"upserted": result.get("upserted"), "total": result.get("total_amount")},
    )
    return result
