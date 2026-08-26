"""Ketoan: Trang Kế Toán phê duyệt cấp 1 các Đề Nghị Thanh Toán từ saleadmin.

Workflow: NV saleadmin tạo (`cho_duyet`) → KT (ở đây) duyệt → `kt_duyet`
                                          → KT từ chối → `kt_tu_choi`
Sau khi `kt_duyet`, CEO duyệt cấp 2 ở app saleadmin để hoàn tất + auto-sync ketoan.

Cùng DB nên đọc/ghi `saleadmin.denghitt` trực tiếp qua ORM (lazy import).
"""
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text as _text
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload, require_app
from shared.db import get_db


router = APIRouter()
_REQ = require_app("ketoan")
_KT_ROLES = ("manager", "admin")


# ── Schemas (local — không phụ thuộc saleadmin) ─────────────────────


class KTApproveBody(BaseModel):
    kt_ghi_chu: Optional[str] = None


class KTRejectBody(BaseModel):
    ly_do: str = Field(..., min_length=1)


class ChiBody(BaseModel):
    tai_khoan: Optional[str] = None
    ghi_chu: Optional[str] = None


_CHI_ROLES = ("manager", "admin", "ceo", "assistant_ceo")


def _denghitt_to_dict(e, name_map: Optional[dict] = None) -> dict:
    """Convert saleadmin.DeNghiTT ORM → dict.

    `name_map` (username → full_name) dùng để gắn thêm `*_ten` cho UI hiển thị
    tên thay vì mã. Caller (`list_denghitt`) batch query một lần để tránh N+1.
    """
    nm = name_map or {}
    return {
        "id": e.id,
        "ngay_de_nghi": e.ngay_de_nghi.isoformat() if e.ngay_de_nghi else None,
        "ma_don": e.ma_don,
        "don_vi_vc": e.don_vi_vc,
        "dvvc_id": e.dvvc_id,
        "so_tien": float(e.so_tien) if e.so_tien else 0,
        "ngay_giao": e.ngay_giao.isoformat() if e.ngay_giao else None,
        "ly_do": e.ly_do,
        "ghi_chu": e.ghi_chu,
        "trang_thai": e.trang_thai,
        "nguoi_tao": e.nguoi_tao,
        "nguoi_tao_ten": nm.get(e.nguoi_tao) if e.nguoi_tao else None,
        "kt_duyet_boi": e.kt_duyet_boi,
        "kt_duyet_boi_ten": nm.get(e.kt_duyet_boi) if e.kt_duyet_boi else None,
        "kt_duyet_luc": e.kt_duyet_luc.isoformat() if e.kt_duyet_luc else None,
        "kt_ghi_chu": e.kt_ghi_chu,
        "nguoi_duyet": e.nguoi_duyet,
        "nguoi_duyet_ten": nm.get(e.nguoi_duyet) if e.nguoi_duyet else None,
        "ngay_duyet": e.ngay_duyet.isoformat() if e.ngay_duyet else None,
        "chung_tu_url": e.chung_tu_url,
        "ref_congno": getattr(e, "ref_congno", None),
        "da_chi": bool(getattr(e, "da_chi", False)),
        "da_chi_ngoai": bool(getattr(e, "da_chi_ngoai", False)),
        "tai_khoan_chi": getattr(e, "tai_khoan_chi", None),
        "ngay_chi": e.ngay_chi.isoformat() if getattr(e, "ngay_chi", None) else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _build_name_map(db: Session, rows: list) -> dict:
    """Batch query shared.users để map username → full_name cho cả nguoi_tao/kt_duyet_boi/nguoi_duyet."""
    from shared.models import User  # lazy
    usernames = {
        u for e in rows
        for u in (e.nguoi_tao, e.kt_duyet_boi, e.nguoi_duyet)
        if u
    }
    if not usernames:
        return {}
    users = db.execute(
        select(User.username, User.full_name).where(User.username.in_(usernames))
    ).all()
    return {u: n for u, n in users}


def _get_or_404(db: Session, did: str):
    from saleadmin.app.models import DeNghiTT  # lazy cross-app
    e = db.get(DeNghiTT, did)
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"DNTT {did} không tồn tại")
    return e


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("/api/de-nghi-tt")
def list_denghitt(
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
    trang_thai: Optional[str] = Query(None, description="lọc theo trang_thai; rỗng = tất cả"),
    limit: int = Query(200, le=500),
    offset: int = 0,
):
    """List denghitt cho trang Kế Toán phê duyệt. Default trả tất cả status mới nhất."""
    from saleadmin.app.models import DeNghiTT  # lazy cross-app
    stmt = select(DeNghiTT).order_by(DeNghiTT.created_at.desc())
    if trang_thai:
        stmt = stmt.where(DeNghiTT.trang_thai == trang_thai)
    stmt = stmt.limit(limit).offset(offset)
    rows = list(db.execute(stmt).scalars())
    name_map = _build_name_map(db, rows)
    return [_denghitt_to_dict(e, name_map) for e in rows]


@router.get("/api/de-nghi-tt/summary")
def summary_denghitt(
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """Đếm theo trạng thái — dùng cho badge UI."""
    from sqlalchemy import func
    from saleadmin.app.models import DeNghiTT  # lazy cross-app
    rows = db.execute(
        select(DeNghiTT.trang_thai, func.count(DeNghiTT.id))
        .group_by(DeNghiTT.trang_thai)
    ).all()
    return {tt: n for tt, n in rows}


@router.get("/api/de-nghi-tt/{did}/detail")
def detail_denghitt(
    did: str,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """Chi tiết 1 DNTT kèm danh sách chứng từ — dùng cho modal KT xem trước khi duyệt."""
    e = _get_or_404(db, did)
    name_map = _build_name_map(db, [e])
    data = _denghitt_to_dict(e, name_map)
    # Lấy danh sách chứng từ
    try:
        from saleadmin.app.models.dntt_attachment import DeNghiTTAttachment
        atts = db.execute(
            select(DeNghiTTAttachment)
            .where(DeNghiTTAttachment.dntt_id == did)
            .order_by(DeNghiTTAttachment.uploaded_at.asc())
        ).scalars().all()
        data["attachments"] = [
            {
                "id": a.id,
                "loai": a.loai,
                "filename": a.filename,
                "url": a.url,
                "size": a.size,
                "ghi_chu": a.ghi_chu,
                "uploaded_at": a.uploaded_at.isoformat() if a.uploaded_at else None,
                "uploaded_by": a.uploaded_by,
            }
            for a in atts
        ]
    except Exception:
        data["attachments"] = []
    return data


@router.post("/api/de-nghi-tt/{did}/kt-approve")
def kt_approve(
    did: str,
    body: KTApproveBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """Kế toán duyệt cấp 1 — cho_duyet → kt_duyet."""
    if user.role not in _KT_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ kế toán (manager)/admin được duyệt cấp 1")
    e = _get_or_404(db, did)
    if e.trang_thai != "cho_duyet":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"DNTT trạng thái {e.trang_thai!r}, KT chỉ duyệt khi cho_duyet",
        )
    e.trang_thai = "kt_duyet"
    e.kt_duyet_boi = user.username
    e.kt_duyet_luc = datetime.now(tz=timezone.utc)
    if body.kt_ghi_chu:
        e.kt_ghi_chu = body.kt_ghi_chu
    db.commit()
    db.refresh(e)
    log_action(
        db, app="ketoan", action="kt_approve_denghitt", user=user, request=request,
        resource=f"denghitt:{did}", payload={"kt_ghi_chu": body.kt_ghi_chu},
    )
    return _denghitt_to_dict(e, _build_name_map(db, [e]))


@router.post("/api/de-nghi-tt/{did}/kt-reject")
def kt_reject(
    did: str,
    body: KTRejectBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """Kế toán từ chối cấp 1 — cho_duyet → kt_tu_choi."""
    if user.role not in _KT_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ kế toán (manager)/admin được từ chối cấp 1")
    e = _get_or_404(db, did)
    if e.trang_thai != "cho_duyet":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"DNTT trạng thái {e.trang_thai!r}, KT chỉ từ chối khi cho_duyet",
        )
    e.trang_thai = "kt_tu_choi"
    e.kt_duyet_boi = user.username
    e.kt_duyet_luc = datetime.now(tz=timezone.utc)
    e.kt_ghi_chu = body.ly_do
    db.commit()
    db.refresh(e)
    log_action(
        db, app="ketoan", action="kt_reject_denghitt", user=user, request=request,
        resource=f"denghitt:{did}", payload={"ly_do": body.ly_do},
    )
    return _denghitt_to_dict(e, _build_name_map(db, [e]))


@router.post("/api/de-nghi-tt/{did}/chi")
def chi_denghitt(
    did: str,
    body: ChiBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """KT bấm CHI 1 Đề Nghị TT đã CEO duyệt → tạo sổ quỹ chi + ChiPhí + đánh dấu
    da_chi (đồng nhất với Đề xuất chi + Trả NCC). Idempotent: chỉ chi khi
    trang_thai='duyet' + chưa da_chi + chưa da_chi_ngoai (chưa chi ở trang NCC).
    Nếu DNTT nối từ đề xuất NCC (ref_congno) → giảm công nợ NCC luôn.
    """
    if user.role not in _CHI_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ Kế Toán/CEO được chi")
    e = _get_or_404(db, did)
    if (e.trang_thai or "") != "duyet":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"DNTT trạng thái {e.trang_thai!r} — chỉ chi khi CEO đã duyệt cuối (duyet).",
        )
    if getattr(e, "da_chi", False):
        raise HTTPException(status.HTTP_409_CONFLICT, "Đề nghị này đã được chi rồi.")
    if getattr(e, "da_chi_ngoai", False):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Khoản này đã được chi ở trang Duyệt ĐX Trả NCC — không chi lại.",
        )

    tk = (body.tai_khoan or "").strip() or None
    # CHẶN chi làm số dư TK âm (anh Quang 2026-08-27)
    if tk:
        from ketoan.app.services.so_quy_auto import assert_du_chi
        assert_du_chi(db, tk, e.so_tien)

    # Tạo sổ quỹ chi + ChiPhí phai_tra ĐVVC (idempotent qua ref_dntt), rồi đánh dấu.
    try:
        from ketoan.app.services.from_saleadmin import sync_so_quy_chi_phi_from_denghitt
        sync_so_quy_chi_phi_from_denghitt(db, e, tai_khoan=tk)
        e.da_chi = True
        e.tai_khoan_chi = tk
        e.ngay_chi = datetime.now(tz=timezone.utc)
        e.chi_boi = user.username
        db.commit()
        db.refresh(e)
    except Exception as ex:
        db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Chi thất bại — sổ quỹ lỗi: {ex}"
        )
    if not getattr(e, "da_chi", False):
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Chi chưa ghi được")

    # Nối NCC: DNTT từ đề xuất trả NCC → giảm công nợ NCC (đánh dấu congno.da_chi).
    _ref_cn = getattr(e, "ref_congno", None)
    if _ref_cn:
        try:
            db.execute(
                _text("""UPDATE muahang.congno
                         SET da_chi = TRUE, tai_khoan_chi = :tk, ngay_chi = now()
                         WHERE id = :c AND da_chi = FALSE"""),
                {"tk": tk, "c": _ref_cn},
            )
            db.commit()
        except Exception:
            db.rollback()

    log_action(
        db, app="ketoan", action="chi_denghitt", user=user, request=request,
        resource=f"denghitt:{did}",
        payload={"tai_khoan": tk, "so_tien": float(e.so_tien or 0)},
    )
    return _denghitt_to_dict(e, _build_name_map(db, [e]))
