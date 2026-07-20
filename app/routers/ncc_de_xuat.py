"""Kế Toán duyệt CẤP 1 cho "Đề xuất trả nợ NCC" của app Mua Hàng.

Source of truth: `muahang.congno` (loai='de_xuat_tra'). KT KHÔNG tạo bản sao —
đọc/ghi trực tiếp qua ORM (lazy import, cùng DB).

Luồng 2 cấp (mirror saleadmin.denghitt):
  NV Mua Hàng đề xuất (cho_duyet) → KT duyệt (ở đây) → kt_duyet → CEO duyệt cuối
  ở app Mua Hàng → duyet (+ bridge ketoan.so_quy).
  KT từ chối → kt_tu_choi (kết thúc).

Mounted KHÔNG prefix trong ketoan/app/main.py (paths đã full /api/ncc-de-xuat...).
"""
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload, require_app
from shared.db import get_db


router = APIRouter()
_REQ = require_app("ketoan")
_KT_ROLES = ("manager", "admin")          # KT duyệt cấp 1
_CEO_ROLES = ("ceo", "admin", "assistant_ceo")  # cấp 2 (để notify)

_MUAHANG_HOST = "https://muahang.qlpps.com"


# ── Schemas ──────────────────────────────────────────────────────────
class KTApproveBody(BaseModel):
    kt_ghi_chu: Optional[str] = None


class KTRejectBody(BaseModel):
    ly_do: str = Field(..., min_length=1)


# ── Helpers ──────────────────────────────────────────────────────────
def _get_or_404(db: Session, cid: str):
    from muahang.app.models import CongNo  # lazy cross-app
    e = db.get(CongNo, cid)
    if not e or e.loai != "de_xuat_tra":
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Đề xuất {cid} không tồn tại")
    return e


def _build_name_map(db: Session, rows: list) -> dict:
    """Batch map username → full_name cho nguoi_tao/kt_duyet_boi/nguoi_duyet."""
    from shared.models import User  # lazy
    usernames = {
        u for e in rows
        for u in (e.nguoi_tao, e.nv_mua_hang, e.kt_duyet_boi, e.nguoi_duyet)
        if u
    }
    if not usernames:
        return {}
    users = db.execute(
        select(User.username, User.full_name).where(User.username.in_(usernames))
    ).all()
    return {u: n for u, n in users}


def _to_dict(e, name_map: Optional[dict] = None) -> dict:
    nm = name_map or {}
    return {
        "id": e.id,
        "ncc_id": e.ncc_id,
        "ncc_name": e.ncc_name,
        "so_tien": float(e.so_tien) if e.so_tien else 0,
        "ngay": e.ngay.isoformat() if e.ngay else None,
        "thang": e.thang,
        "ref_order_id": e.ref_order_id,
        "mo_ta": e.mo_ta,
        "trang_thai": e.trang_thai,
        "nguoi_tao": e.nguoi_tao,
        "nguoi_tao_ten": nm.get(e.nguoi_tao) if e.nguoi_tao else None,
        "nv_mua_hang": e.nv_mua_hang,
        "nv_mua_hang_ten": nm.get(e.nv_mua_hang) if e.nv_mua_hang else None,
        "kt_duyet_boi": e.kt_duyet_boi,
        "kt_duyet_boi_ten": nm.get(e.kt_duyet_boi) if e.kt_duyet_boi else None,
        "kt_duyet_luc": e.kt_duyet_luc.isoformat() if e.kt_duyet_luc else None,
        "kt_ghi_chu": e.kt_ghi_chu,
        "nguoi_duyet": e.nguoi_duyet,
        "nguoi_duyet_ten": nm.get(e.nguoi_duyet) if e.nguoi_duyet else None,
        "ngay_duyet": e.ngay_duyet.isoformat() if e.ngay_duyet else None,
        "ghi_chu_duyet": e.ghi_chu_duyet,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _ceo_usernames(db: Session) -> list[str]:
    from shared.models import User  # lazy
    rows = db.execute(
        select(User.username)
        .where(User.role.in_(_CEO_ROLES))
        .where(User.active.is_(True))
    ).scalars().all()
    return [u for u in rows if u]


def _safe_notify(db: Session, *, targets=None, target=None, by: str, **kwargs) -> None:
    """Gửi noti fail-soft — không bao giờ làm hỏng giao dịch."""
    try:
        if targets:
            from shared.services.notify import notify_many
            notify_many(db, targets, exclude=[by], created_by=by, **kwargs)
        elif target:
            from shared.services.notify import notify
            notify(db, target=target, created_by=by, **kwargs)
    except Exception:
        import logging
        logging.getLogger(__name__).warning("ncc_de_xuat notify failed", exc_info=True)


# ── Endpoints ────────────────────────────────────────────────────────
@router.get("/api/ncc-de-xuat")
def list_ncc_de_xuat(
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
    trang_thai: Optional[str] = Query(None, description="lọc trạng thái; rỗng = tất cả"),
    limit: int = Query(200, le=500),
    offset: int = 0,
):
    """Danh sách đề xuất trả NCC cho trang Kế Toán duyệt. Mặc định mới nhất trước."""
    from muahang.app.models import CongNo  # lazy
    stmt = (
        select(CongNo)
        .where(CongNo.loai == "de_xuat_tra")
        .order_by(CongNo.created_at.desc())
    )
    if trang_thai:
        stmt = stmt.where(CongNo.trang_thai == trang_thai)
    stmt = stmt.limit(limit).offset(offset)
    rows = list(db.execute(stmt).scalars())
    name_map = _build_name_map(db, rows)
    return [_to_dict(e, name_map) for e in rows]


@router.get("/api/ncc-de-xuat/summary")
def summary_ncc_de_xuat(
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """Đếm theo trạng thái — dùng cho badge UI."""
    from muahang.app.models import CongNo  # lazy
    rows = db.execute(
        select(CongNo.trang_thai, func.count(CongNo.id))
        .where(CongNo.loai == "de_xuat_tra")
        .group_by(CongNo.trang_thai)
    ).all()
    return {(tt or ""): n for tt, n in rows}


@router.get("/api/ncc-de-xuat/{cid}/detail")
def detail_ncc_de_xuat(
    cid: str,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """Chi tiết 1 đề xuất kèm chứng từ — cho modal KT xem trước khi duyệt."""
    e = _get_or_404(db, cid)
    data = _to_dict(e, _build_name_map(db, [e]))
    try:
        data["attachments"] = [
            {
                "id": a.id, "filename": a.filename, "url": a.url,
                "mimetype": a.mimetype, "size": a.size,
                "uploaded_at": a.uploaded_at.isoformat() if a.uploaded_at else None,
                "uploaded_by": a.uploaded_by,
            }
            for a in (e.attachments or [])
        ]
    except Exception:
        data["attachments"] = []
    return data


@router.post("/api/ncc-de-xuat/{cid}/kt-approve")
def kt_approve(
    cid: str,
    body: KTApproveBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """Kế Toán duyệt cấp 1 — cho_duyet → kt_duyet. Sau đó chờ CEO duyệt ở Mua Hàng."""
    if user.role not in _KT_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ kế toán (manager)/admin được duyệt cấp 1")
    e = _get_or_404(db, cid)
    if e.trang_thai != "cho_duyet":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Đề xuất đang ở '{e.trang_thai}', KT chỉ duyệt khi cho_duyet",
        )
    e.trang_thai = "kt_duyet"
    e.kt_duyet_boi = user.username
    e.kt_duyet_luc = datetime.now(tz=timezone.utc)
    if body.kt_ghi_chu:
        e.kt_ghi_chu = body.kt_ghi_chu
    db.commit()
    db.refresh(e)
    # Notify CEO: đề xuất đã qua KT, chờ duyệt cuối
    _safe_notify(
        db, targets=_ceo_usernames(db), by=user.username,
        source_app="muahang", event_type="congno:pending_ceo",
        title=f"[Đề xuất trả NCC] Kế Toán đã duyệt — {e.ncc_name or e.ncc_id}",
        message=f"{int(e.so_tien or 0):,}đ — chờ CEO duyệt chi",
        ref_type="congno", ref_id=e.id, url=f"{_MUAHANG_HOST}/", severity="info",
    )
    db.commit()
    log_action(
        db, app="ketoan", action="kt_approve_congno_dexuat", user=user, request=request,
        resource=f"congno:{cid}", payload={"kt_ghi_chu": body.kt_ghi_chu},
    )
    return _to_dict(e, _build_name_map(db, [e]))


@router.post("/api/ncc-de-xuat/{cid}/kt-reject")
def kt_reject(
    cid: str,
    body: KTRejectBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """Kế Toán từ chối cấp 1 — cho_duyet → kt_tu_choi (kết thúc)."""
    if user.role not in _KT_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ kế toán (manager)/admin được từ chối cấp 1")
    e = _get_or_404(db, cid)
    if e.trang_thai != "cho_duyet":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Đề xuất đang ở '{e.trang_thai}', KT chỉ từ chối khi cho_duyet",
        )
    e.trang_thai = "kt_tu_choi"
    e.kt_duyet_boi = user.username
    e.kt_duyet_luc = datetime.now(tz=timezone.utc)
    e.kt_ghi_chu = body.ly_do
    db.commit()
    db.refresh(e)
    # Notify người tạo: KT từ chối
    _safe_notify(
        db, target=e.nguoi_tao, by=user.username,
        source_app="muahang", event_type="congno:rejected",
        title=f"[Đề xuất trả NCC] Kế Toán từ chối — {e.ncc_name or e.ncc_id}",
        message=body.ly_do, ref_type="congno", ref_id=e.id, severity="warning",
    )
    db.commit()
    log_action(
        db, app="ketoan", action="kt_reject_congno_dexuat", user=user, request=request,
        resource=f"congno:{cid}", payload={"ly_do": body.ly_do},
    )
    return _to_dict(e, _build_name_map(db, [e]))
