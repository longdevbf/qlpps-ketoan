"""Kỳ Kế Toán — đóng kỳ + LN giữ lại + P&L snapshot.

Endpoints:
    GET    /api/ky-ke-toan                         (list 12 kỳ gần nhất)
    GET    /api/ky-ke-toan/ln-giu-lai/luy-ke       (LN giữ lại lũy kế hiện tại)
    GET    /api/ky-ke-toan/{thang}                 (chi tiết 1 kỳ + snapshot)
    POST   /api/ky-ke-toan/{thang}/chot            (chốt kỳ)
    POST   /api/ky-ke-toan/{thang}/mo              (mở lại — admin/ceo)

Quy ước:
  - thang VARCHAR(7) định dạng 'YYYY-MM'
  - Chốt kỳ T → kỳ T-1 phải đã chốt (trừ kỳ đầu tiên có dữ liệu)
  - Mở kỳ T → kỳ T+1 phải mở trước (cascade)
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import BaoCaoPLSnapshot, KyKeToan
from ..schemas.ky_ke_toan import (
    ChotKyResponse, KyKeToanDetailOut, KyKeToanOut, LNGiuLaiLuyKeOut,
)
from ..schemas.pl_snapshot import PLSnapshotOut
from ..services.period_close import (
    PeriodCloseError, chot_ky, get_ln_giu_lai_luy_ke, mo_ky,
)
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)
_THANG_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


def _validate_thang(thang: str) -> str:
    import re
    if not re.match(_THANG_PATTERN, thang):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"thang phải dạng YYYY-MM, nhận: {thang!r}",
        )
    return thang


# ─── List 12 kỳ gần nhất ─────────────────────────────────────────────────────

@router.get("", response_model=list[KyKeToanOut])
def list_ky_ke_toan(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """List 12 kỳ kế toán gần nhất (theo thang DESC)."""
    items = db.execute(
        select(KyKeToan).order_by(KyKeToan.thang.desc()).limit(12)
    ).scalars().all()
    return items


# ─── LN giữ lại lũy kế ───────────────────────────────────────────────────────

@router.get("/ln-giu-lai/luy-ke", response_model=LNGiuLaiLuyKeOut)
def ln_giu_lai_luy_ke(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """LN giữ lại lũy kế hiện tại = kỳ chốt mới nhất.ln_giu_lai_cuoi_ky."""
    return get_ln_giu_lai_luy_ke(db)


# ─── Detail 1 kỳ ─────────────────────────────────────────────────────────────

@router.get("/{thang}", response_model=KyKeToanDetailOut)
def get_ky(
    thang: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Chi tiết 1 kỳ + P&L snapshot (nếu đã chốt)."""
    _validate_thang(thang)
    ky = db.get(KyKeToan, thang)
    if ky is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Kỳ {thang} chưa được khởi tạo (chưa từng chốt/mở)",
        )
    snap_out = None
    if ky.pl_snapshot_id:
        snap = db.get(BaoCaoPLSnapshot, ky.pl_snapshot_id)
        if snap is not None:
            snap_out = PLSnapshotOut.model_validate(snap, from_attributes=True)
    out = KyKeToanDetailOut.model_validate(ky, from_attributes=True)
    out.pl_snapshot = snap_out
    return out


# ─── Chốt kỳ ─────────────────────────────────────────────────────────────────

@router.post(
    "/{thang}/chot",
    response_model=ChotKyResponse,
    status_code=status.HTTP_200_OK,
)
def chot(
    thang: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Chốt kỳ kế toán tháng `thang`.

    Quy tắc:
      - Kỳ trước phải đã chốt (trừ tháng đầu tiên có dữ liệu)
      - Kỳ này chưa chốt
      - Tự build P&L snapshot + tính LN giữ lại cuối kỳ
    """
    _validate_thang(thang)
    if user.role not in ("admin", "ceo", "assistant_ceo", "manager", "kt"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Không có quyền chốt kỳ",
        )
    try:
        result = chot_ky(db, thang, by_user=user.username)
    except PeriodCloseError as e:
        raise HTTPException(e.status_code, detail={"code": e.code, "message": e.message})

    log_action(
        db, app="ketoan", action="chot_ky_ke_toan", user=user, request=request,
        resource=f"ky_ke_toan:{thang}",
        payload={
            "thang": thang,
            "lnst_ky": float(result["lnst_ky"]),
            "ln_giu_lai_cuoi_ky": float(result["ln_giu_lai_cuoi_ky"]),
            "co_tuc": float(result["co_tuc_da_chia"]),
            "trich_quy": float(result["trich_quy_ky"]),
        },
    )
    return result


# ─── Mở lại kỳ ───────────────────────────────────────────────────────────────

@router.post("/{thang}/mo", status_code=status.HTTP_200_OK)
def mo(
    thang: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Mở lại kỳ đã chốt — chỉ admin/ceo. Cascade check kỳ sau."""
    _validate_thang(thang)
    if user.role not in ("admin", "ceo"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Chỉ admin/ceo được mở lại kỳ đã chốt",
        )
    try:
        result = mo_ky(db, thang, by_user=user.username)
    except PeriodCloseError as e:
        raise HTTPException(e.status_code, detail={"code": e.code, "message": e.message})

    log_action(
        db, app="ketoan", action="mo_ky_ke_toan", user=user, request=request,
        resource=f"ky_ke_toan:{thang}",
        payload={"thang": thang, "snapshot_da_xoa": result.get("snapshot_da_xoa")},
    )
    return result
