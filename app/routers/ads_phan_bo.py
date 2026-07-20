"""API router — phân bổ chi phí ads (Phase 6A).

Endpoints:
    POST   /api/ads-phan-bo/recalc/{thang}       (admin/kt only)
    GET    /api/ads-phan-bo                       (filter: thang_chi, nhom, quote_number)
    GET    /api/ads-phan-bo/summary?thang=        (tóm tắt 1 tháng)
    GET    /api/ads-phan-bo/cohort?from=&to=      (ma trận tháng chi × tháng HT)
"""
from datetime import datetime
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ._deps import require_ketoan_user
from ..services.ads_phan_bo import (
    NHOM_MASTERS,
    get_pool_breakdown,
    recalc_ads_phan_bo,
)


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


# Roles được phép trigger recalc (DML)
_RECALC_ROLES = ("admin", "ceo", "assistant_ceo", "manager", "kt")


def _validate_thang(thang: str) -> str:
    """'YYYY-MM' format check."""
    if not thang or len(thang) != 7 or thang[4] != "-":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"thang phải là 'YYYY-MM', got {thang!r}",
        )
    try:
        datetime.strptime(thang, "%Y-%m")
    except ValueError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"thang không hợp lệ: {thang!r}",
        )
    return thang


# ────────────────────────────────────────────────────────────────────────
# POST /recalc/{thang}
# ────────────────────────────────────────────────────────────────────────

@router.post("/recalc/{thang}")
def recalc(
    thang: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Tính lại bảng phân bổ ads cho tháng X.

    Tác vụ:
      1. DELETE ketoan.ads_phan_bo_don WHERE thang_chi_ads = :thang
      2. Group ads theo nhóm master + redistribute Khác chia 3
      3. List quotes chốt T X (duyet_status='approved' AND duyet_luc IN T X)
      4. Phân bổ pool nhóm theo % giá trị nhóm trong từng đơn
      5. Sync vc_status từ saleadmin.vanchuyen
      6. Invalidate PL cache

    Auth: admin/kt only (Reject role 'kd', 'mh', 'mkt', 'sa', 'hr', 'nhan_vien').
    """
    if user.role not in _RECALC_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Role {user.role!r} không có quyền recalc ads phân bổ",
        )
    _validate_thang(thang)

    try:
        summary = recalc_ads_phan_bo(db, thang)
    except (ProgrammingError, OperationalError) as e:
        db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"DB error khi recalc: {str(e)[:200]}",
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    log_action(
        db, app="ketoan", action="ads_phan_bo_recalc", user=user,
        payload={"thang": thang, "summary": summary},
    )
    db.commit()
    return {"ok": True, **summary}


# ────────────────────────────────────────────────────────────────────────
# GET / (list with filter)
# ────────────────────────────────────────────────────────────────────────

@router.get("")
def list_phan_bo(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    thang_chi: Optional[str] = Query(None, description="'YYYY-MM' filter"),
    nhom: Optional[str] = Query(None, description="'Đồ Gỗ' | 'Đồ Mây' | 'Dự Án'"),
    quote_number: Optional[str] = Query(None),
    loai: Optional[str] = Query(None, description="theo_nhom|redistribute_khac|no_match"),
    vc_status: Optional[str] = Query(None),
    thang_hoan_thanh: Optional[str] = Query(None),
    limit: int = Query(500, le=2000),
):
    """List rows ads_phan_bo_don với filter."""
    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if thang_chi:
        _validate_thang(thang_chi)
        where.append("thang_chi_ads = :tc")
        params["tc"] = thang_chi
    if nhom:
        if nhom not in NHOM_MASTERS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"nhom phải IN {NHOM_MASTERS}, got {nhom!r}",
            )
        where.append("nhom_master = :nm")
        params["nm"] = nhom
    if quote_number:
        where.append("quote_number = :qn")
        params["qn"] = quote_number
    if loai:
        where.append("loai_phan_bo = :lp")
        params["lp"] = loai
    if vc_status:
        where.append("COALESCE(vc_status, '') = :vs")
        params["vs"] = vc_status
    if thang_hoan_thanh:
        _validate_thang(thang_hoan_thanh)
        where.append("thang_hoan_thanh = :tht")
        params["tht"] = thang_hoan_thanh

    sql = f"""
        SELECT id, thang_chi_ads, nhom_master, quote_number, ngay_chot,
               value_nhom_trong_don, ty_le_pool, so_tien_phan_bo,
               loai_phan_bo, vc_status, thang_hoan_thanh, cpa_nhom_snapshot,
               created_at, updated_at
        FROM ketoan.ads_phan_bo_don
        WHERE {' AND '.join(where)}
        ORDER BY thang_chi_ads DESC, nhom_master, ngay_chot DESC NULLS LAST,
                 quote_number NULLS LAST
        LIMIT :lim
    """
    params["lim"] = limit
    try:
        rows = db.execute(text(sql), params).mappings().all()
    except (ProgrammingError, OperationalError) as e:
        db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"DB error: {str(e)[:200]}",
        )

    # Convert Decimal → float cho JSON
    out = []
    for r in rows:
        d = dict(r)
        for k in (
            "value_nhom_trong_don", "ty_le_pool", "so_tien_phan_bo",
            "cpa_nhom_snapshot",
        ):
            if d.get(k) is not None:
                d[k] = float(d[k])
        if d.get("ngay_chot") is not None:
            d["ngay_chot"] = str(d["ngay_chot"])
        if d.get("created_at") is not None:
            d["created_at"] = d["created_at"].isoformat()
        if d.get("updated_at") is not None:
            d["updated_at"] = d["updated_at"].isoformat()
        out.append(d)

    return {"data": out, "count": len(out)}


# ────────────────────────────────────────────────────────────────────────
# GET /summary?thang=
# ────────────────────────────────────────────────────────────────────────

@router.get("/summary")
def summary(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    thang: str = Query(..., description="'YYYY-MM'"),
):
    """Tóm tắt 1 tháng — pool sau khi redistribute Khác + breakdown nhóm.

    Đọc từ ketoan.ads_phan_bo_don (đã được recalc trước đó).
    Nếu chưa recalc lần nào → trả pool=0.
    """
    _validate_thang(thang)
    try:
        return get_pool_breakdown(db, thang)
    except (ProgrammingError, OperationalError) as e:
        db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"DB error: {str(e)[:200]}",
        )


# ────────────────────────────────────────────────────────────────────────
# GET /cohort?from=&to=
# ────────────────────────────────────────────────────────────────────────

@router.get("/cohort")
def cohort(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu: str = Query(..., alias="from", description="'YYYY-MM'"),
    den: str = Query(..., alias="to", description="'YYYY-MM'"),
):
    """Ma trận tháng chi × tháng hoàn thành × nhóm.

    Trả mỗi cell:
      (thang_chi_ads, thang_hoan_thanh, nhom_master, so_tien_phan_bo, so_dong)

    UI dùng để vẽ heatmap "ads tháng X chảy về CP BH tháng Y".
    """
    _validate_thang(tu)
    _validate_thang(den)
    if tu > den:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"from ({tu}) phải <= to ({den})",
        )

    sql = """
        SELECT thang_chi_ads,
               thang_hoan_thanh,
               nhom_master,
               SUM(so_tien_phan_bo)::float AS so_tien_phan_bo,
               COUNT(*)::int AS so_dong
        FROM ketoan.ads_phan_bo_don
        WHERE thang_chi_ads BETWEEN :tu AND :den
        GROUP BY thang_chi_ads, thang_hoan_thanh, nhom_master
        ORDER BY thang_chi_ads, thang_hoan_thanh NULLS LAST, nhom_master
    """
    try:
        rows = db.execute(text(sql), {"tu": tu, "den": den}).mappings().all()
    except (ProgrammingError, OperationalError) as e:
        db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"DB error: {str(e)[:200]}",
        )

    return {"tu": tu, "den": den, "rows": [dict(r) for r in rows]}
