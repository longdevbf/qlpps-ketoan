"""Quản lý quỹ doanh nghiệp — cây 1 bảng `quy_dn`.

Endpoints (mount /api/quy):
    GET  /api/quy/tree                    — cây 5 root + children
    GET  /api/quy/thanh-tien/{thang}      — auto compute từ DT tháng (YYYY-MM)
    POST /api/quy                         — thêm quỹ (admin only)
    PUT  /api/quy/{id}                    — sửa quỹ
    PUT  /api/quy/{id}/config             — chỉnh % (admin only)
    DELETE /api/quy/{id}                  — xoá (cascade children)
    POST /api/quy/{id}/chi                — chi quỹ legacy (đã thay bằng giao_dich_router)

Endpoints (mount /api/quy-dn — qua `giao_dich_router`):
    POST   /api/quy-dn/{quy_id}/nap         — nạp tiền (loại=thu, +so_du)
    POST   /api/quy-dn/{quy_id}/chi         — chi tiền (loại=chi, -so_du)
    GET    /api/quy-dn/{quy_id}/giao-dich   — list giao dịch
    GET    /api/quy-dn/{quy_id}/so-du       — so_du hiện tại + last_giao_dich_ngay
    POST   /api/quy-dn/{quy_id}/recalc      — recalc so_du (admin/ceo)
    DELETE /api/quy-dn/giao-dich/{gd_id}    — void giao dịch (admin/ceo)

Compute logic:
- Quỹ root nguon='doanh_thu_pct' → thanh_tien = ty_le_pct% × DT_tháng
- Quỹ child nguon='parent_pct'   → thanh_tien = ty_le_pct% × parent.thanh_tien
- Quỹ root nguon='hcns_cong_doan' → đọc HCNS hcns.cong_doan_fund
- Quỹ root nguon='manual' → 0 (chỉ tracking so_du)
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db
from shared.services.employees import ten_nv

from ..models import DoanhThu, QuyDN, QuyDNGiaoDich
from ..schemas.quy_dn_giao_dich import QuyDNGiaoDichCreate
from ..services.quy_dn_calc import (
    chi_tu_quy, nap_quy, recalc_so_du, void_giao_dich,
)
from ._deps import require_ketoan_user


router = APIRouter()
giao_dich_router = APIRouter()
_AUTH = Depends(require_ketoan_user)
_ADMIN_ROLES = {"admin", "ceo", "assistant_ceo"}


def _can_admin(user: JWTPayload) -> bool:
    return user.role in _ADMIN_ROLES


# ──────────────────────── Schemas ────────────────────────

class QuyIn(BaseModel):
    ten_quy: str
    parent_id: Optional[int] = None
    nguon_compute: str = "manual"     # 'manual' | 'doanh_thu_pct' | 'parent_pct' | 'hcns_cong_doan'
    ty_le_pct: Optional[float] = 0
    thu_tu: Optional[int] = 0
    ghi_chu: Optional[str] = None
    active: Optional[bool] = True


class QuyConfigIn(BaseModel):
    ty_le_pct: float
    nguon_compute: Optional[str] = None  # cho phép đổi nguồn nếu cần


class QuyChiIn(BaseModel):
    so_tien: float
    mo_ta: Optional[str] = None


# ──────────────────────── Helpers ────────────────────────

def _serialize(q: QuyDN, thanh_tien: float = 0.0) -> dict[str, Any]:
    return {
        "id": q.id,
        "ten_quy": q.ten_quy,
        "parent_id": q.parent_id,
        "nguon_compute": q.nguon_compute,
        "ty_le_pct": float(q.ty_le_pct or 0),
        "thu_tu": int(q.thu_tu or 0),
        "so_du": float(q.so_du or 0),
        "ghi_chu": q.ghi_chu or "",
        "active": bool(q.active),
        "thanh_tien": round(thanh_tien, 2),
    }


def _doanh_thu_thang(db: Session, thang: str) -> Decimal:
    """Tổng DoanhThu trong tháng (YYYY-MM)."""
    try:
        y, m = thang.split("-")
        first = date(int(y), int(m), 1)
        if int(m) == 12:
            last = date(int(y), 12, 31)
        else:
            from datetime import timedelta
            last = date(int(y), int(m) + 1, 1) - timedelta(days=1)
    except Exception:
        return Decimal("0")

    total = db.execute(
        select(func.coalesce(func.sum(DoanhThu.so_tien), 0))
        .where(DoanhThu.ngay >= first, DoanhThu.ngay <= last)
    ).scalar() or Decimal("0")
    return Decimal(str(total))


def _cong_doan_thang(db: Session, thang: str) -> Decimal:
    """Đọc tổng quỹ Công Đoàn (so_du_luy_ke) từ hcns.cong_doan_fund tháng (YYYY-MM).

    Wrap savepoint để raw SQL fail không abort outer transaction.
    """
    sp = db.begin_nested()
    try:
        rec = db.execute(text("""
            SELECT so_du_luy_ke
            FROM hcns.cong_doan_fund
            WHERE thang = :thang
            LIMIT 1
        """), {"thang": thang}).scalar()
        sp.commit()
        return Decimal(str(rec or 0))
    except Exception:
        sp.rollback()
        return Decimal("0")


def _compute_tree(db: Session, thang: str) -> dict[int, float]:
    """Tính thanh_tien cho từng quỹ trong tháng. Return {quy_id: thanh_tien}."""
    quy_list = db.execute(
        select(QuyDN).order_by(QuyDN.thu_tu, QuyDN.id)
    ).scalars().all()

    dt = _doanh_thu_thang(db, thang)
    cd = _cong_doan_thang(db, thang)

    out: dict[int, float] = {}
    # Pass 1: roots
    for q in quy_list:
        if q.parent_id is not None:
            continue
        if q.nguon_compute == "doanh_thu_pct":
            out[q.id] = float(dt) * float(q.ty_le_pct or 0) / 100.0
        elif q.nguon_compute == "hcns_cong_doan":
            out[q.id] = float(cd)
        else:
            out[q.id] = 0.0
    # Pass 2: children (max depth 2 — child + grandchild)
    # Run multiple passes để cover grandchildren
    for _ in range(3):
        for q in quy_list:
            if q.parent_id is None:
                continue
            parent_val = out.get(q.parent_id, 0.0)
            if q.nguon_compute == "parent_pct":
                out[q.id] = parent_val * float(q.ty_le_pct or 0) / 100.0
            else:
                out[q.id] = 0.0
    return out


def _get_or_404(db: Session, qid: int) -> QuyDN:
    q = db.get(QuyDN, qid)
    if not q:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy quỹ")
    return q


# ──────────────────────── Endpoints ────────────────────────

@router.get("/tree")
def get_tree(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    thang: Optional[str] = None,
) -> dict[str, Any]:
    """Trả cây quỹ (sort theo thu_tu).

    Nếu có ?thang=YYYY-MM → kèm thanh_tien tự động.
    """
    if not thang:
        thang = datetime.now().strftime("%Y-%m")

    quy_list = db.execute(
        select(QuyDN).order_by(QuyDN.thu_tu, QuyDN.id)
    ).scalars().all()

    tt_map = _compute_tree(db, thang)

    by_parent: dict[Optional[int], list[dict]] = {}
    for q in quy_list:
        by_parent.setdefault(q.parent_id, []).append(_serialize(q, tt_map.get(q.id, 0)))

    def _attach(parent_id: Optional[int]) -> list[dict]:
        out = []
        for item in by_parent.get(parent_id, []):
            item["children"] = _attach(item["id"])
            out.append(item)
        return out

    return {
        "thang": thang,
        "doanh_thu_thang": float(_doanh_thu_thang(db, thang)),
        "tree": _attach(None),
        "can_admin": _can_admin(user),
    }


@router.get("/thanh-tien/{thang}")
def get_thanh_tien(
    thang: str,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Thanh tiền tháng — flat list cho dashboard / export."""
    quy_list = db.execute(
        select(QuyDN).order_by(QuyDN.thu_tu, QuyDN.id)
    ).scalars().all()
    tt = _compute_tree(db, thang)
    return {
        "thang": thang,
        "doanh_thu_thang": float(_doanh_thu_thang(db, thang)),
        "items": [_serialize(q, tt.get(q.id, 0)) for q in quy_list],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_quy(
    body: QuyIn,
    request: Request,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    if not _can_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ admin/CEO được thêm quỹ")

    ten = (body.ten_quy or "").strip()
    if not ten:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Thiếu tên quỹ")

    if body.parent_id is not None:
        _get_or_404(db, body.parent_id)

    if db.execute(select(QuyDN).where(QuyDN.ten_quy == ten)).scalar_one_or_none():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tên quỹ đã tồn tại")

    q = QuyDN(
        ten_quy=ten,
        parent_id=body.parent_id,
        nguon_compute=body.nguon_compute or "manual",
        ty_le_pct=Decimal(str(body.ty_le_pct or 0)),
        thu_tu=int(body.thu_tu or 0),
        ghi_chu=body.ghi_chu or None,
        active=True if body.active is None else bool(body.active),
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    log_action(
        db, app="ketoan", action="quy_create",
        user=user, request=request, resource=f"quy:{q.id}",
        payload={"ten": ten, "nguon": q.nguon_compute, "pct": float(q.ty_le_pct)},
    )
    return _serialize(q)


@router.put("/{qid}")
def update_quy(
    qid: int,
    body: QuyIn,
    request: Request,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    if not _can_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ admin/CEO được sửa quỹ")
    q = _get_or_404(db, qid)

    if body.ten_quy is not None:
        ten = body.ten_quy.strip()
        if not ten:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Thiếu tên quỹ")
        q.ten_quy = ten
    if body.parent_id is not None:
        if body.parent_id == qid:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không thể là parent của chính nó")
        if body.parent_id != 0:
            _get_or_404(db, body.parent_id)
            q.parent_id = body.parent_id
        else:
            q.parent_id = None
    if body.nguon_compute is not None:
        q.nguon_compute = body.nguon_compute
    if body.ty_le_pct is not None:
        q.ty_le_pct = Decimal(str(body.ty_le_pct))
    if body.thu_tu is not None:
        q.thu_tu = int(body.thu_tu)
    if body.ghi_chu is not None:
        q.ghi_chu = body.ghi_chu or None
    if body.active is not None:
        q.active = bool(body.active)

    db.commit()
    db.refresh(q)
    log_action(db, app="ketoan", action="quy_update", user=user, request=request, resource=f"quy:{qid}")
    return _serialize(q)


@router.put("/{qid}/config")
def update_config(
    qid: int,
    body: QuyConfigIn,
    request: Request,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Endpoint riêng cho CEO chỉnh % nhanh — không đụng các field khác."""
    if not _can_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ admin/CEO được chỉnh tỷ lệ")
    q = _get_or_404(db, qid)
    old_pct = float(q.ty_le_pct or 0)
    q.ty_le_pct = Decimal(str(body.ty_le_pct))
    if body.nguon_compute is not None:
        q.nguon_compute = body.nguon_compute
    db.commit()
    db.refresh(q)
    log_action(
        db, app="ketoan", action="quy_config_update",
        user=user, request=request, resource=f"quy:{qid}",
        payload={"old_pct": old_pct, "new_pct": float(q.ty_le_pct)},
    )
    return _serialize(q)


@router.delete("/{qid}")
def delete_quy(
    qid: int,
    request: Request,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    if not _can_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ admin/CEO được xoá quỹ")
    q = _get_or_404(db, qid)
    if q.nguon_compute == "hcns_cong_doan":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Quỹ Công Đoàn lấy từ HCNS, không xoá được")
    ten = q.ten_quy
    db.delete(q)
    db.commit()
    log_action(
        db, app="ketoan", action="quy_delete",
        user=user, request=request, resource=f"quy:{qid}",
        payload={"ten": ten},
    )
    return {"ok": True}


@router.post("/{qid}/chi")
def chi_quy(
    qid: int,
    body: QuyChiIn,
    request: Request,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Chi quỹ — giảm so_du, log audit."""
    # Chi quỹ = rút tiền quỹ DN → chỉ CEO/admin + KHÔNG cho âm (đồng bộ chi_tien_quy
    # bản mới + chốt chặn số dư âm 2026-08-27). (anh Quang 2026-08-31)
    if user.role not in ("admin", "ceo", "assistant_ceo"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ CEO/admin được chi quỹ")
    q = _get_or_404(db, qid)
    if q.nguon_compute == "hcns_cong_doan":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Quỹ Công Đoàn chi qua HCNS, không chi qua endpoint này",
        )
    so_tien = Decimal(str(body.so_tien))
    if so_tien <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Số tiền chi phải > 0")
    if (q.so_du or Decimal("0")) - so_tien < 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Số dư quỹ chỉ còn {int(q.so_du or 0):,}đ — không đủ chi {int(so_tien):,}đ (sẽ âm)",
        )

    q.so_du = (q.so_du or Decimal("0")) - so_tien
    db.commit()
    log_action(
        db, app="ketoan", action="quy_chi",
        user=user, request=request, resource=f"quy:{qid}",
        payload={"so_tien": float(so_tien), "mo_ta": body.mo_ta or "", "so_du_moi": float(q.so_du)},
    )
    return _serialize(q)


# ──────────────────────── Giao dịch quỹ (mount /api/quy-dn) ────────────────────────


def _serialize_gd(gd: QuyDNGiaoDich) -> dict[str, Any]:
    return {
        "id": gd.id,
        "quy_id": gd.quy_id,
        "ngay": gd.ngay.isoformat() if gd.ngay else None,
        "loai": gd.loai,
        "so_tien": float(gd.so_tien or 0),
        "noi_dung": gd.noi_dung or "",
        "source_type": gd.source_type or "",
        "source_id": gd.source_id or "",
        "tai_khoan_id": gd.tai_khoan_id,
        "ghi_chu": gd.ghi_chu or "",
        "created_by": gd.created_by or "",
        "created_at": gd.created_at.isoformat() if gd.created_at else None,
    }


@giao_dich_router.post("/{quy_id}/nap", status_code=status.HTTP_201_CREATED)
def nap_tien_quy(
    quy_id: int,
    body: QuyDNGiaoDichCreate,
    request: Request,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Nạp tiền vào quỹ — tăng so_du."""
    quy = db.get(QuyDN, quy_id)
    if not quy:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quỹ không tồn tại")
    if quy.nguon_compute == "hcns_cong_doan":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Quỹ Công Đoàn lấy từ HCNS, không nạp qua endpoint này",
        )
    gd = nap_quy(
        db, quy_id=quy_id, so_tien=body.so_tien, ngay=body.ngay,
        noi_dung=body.noi_dung, source_type="manual",
        tai_khoan_id=body.tai_khoan_id, ghi_chu=body.ghi_chu,
        by_user=user.username,
    )
    db.commit()
    db.refresh(gd)
    db.refresh(quy)
    log_action(
        db, app="ketoan", action="quy_nap",
        user=user, request=request, resource=f"quy:{quy_id}",
        payload={
            "gd_id": gd.id, "so_tien": float(body.so_tien),
            "so_du_moi": float(quy.so_du),
        },
    )
    return {
        "giao_dich": _serialize_gd(gd),
        "so_du_moi": float(quy.so_du),
    }


@giao_dich_router.post("/{quy_id}/chi", status_code=status.HTTP_201_CREATED)
def chi_tien_quy(
    quy_id: int,
    body: QuyDNGiaoDichCreate,
    request: Request,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Chi tiền từ quỹ — giảm so_du.

    Mặc định chặn nếu vượt số dư. Truyền `allow_negative=true` để bypass
    (chỉ admin/CEO mới nên dùng).
    """
    quy = db.get(QuyDN, quy_id)
    if not quy:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quỹ không tồn tại")
    if quy.nguon_compute == "hcns_cong_doan":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Quỹ Công Đoàn chi qua HCNS, không chi qua endpoint này",
        )

    allow_neg = bool(body.allow_negative)
    if allow_neg and not _can_admin(user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Chỉ admin/CEO mới được cho quỹ âm",
        )

    gd = chi_tu_quy(
        db, quy_id=quy_id, so_tien=body.so_tien, ngay=body.ngay,
        noi_dung=body.noi_dung, source_type="manual",
        tai_khoan_id=body.tai_khoan_id, ghi_chu=body.ghi_chu,
        by_user=user.username, allow_negative=allow_neg,
    )
    db.commit()
    db.refresh(gd)
    db.refresh(quy)
    log_action(
        db, app="ketoan", action="quy_chi_v2",
        user=user, request=request, resource=f"quy:{quy_id}",
        payload={
            "gd_id": gd.id, "so_tien": float(body.so_tien),
            "so_du_moi": float(quy.so_du),
            "allow_negative": allow_neg,
        },
    )
    return {
        "giao_dich": _serialize_gd(gd),
        "so_du_moi": float(quy.so_du),
    }


@giao_dich_router.get("/{quy_id}/giao-dich")
def list_giao_dich_quy(
    quy_id: int,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    loai: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
    offset: int = 0,
) -> dict[str, Any]:
    """List giao dịch quỹ — filter `from`/`to`/`loai`."""
    quy = db.get(QuyDN, quy_id)
    if not quy:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quỹ không tồn tại")

    stmt = select(QuyDNGiaoDich).where(QuyDNGiaoDich.quy_id == quy_id)
    if from_date:
        try:
            stmt = stmt.where(QuyDNGiaoDich.ngay >= date.fromisoformat(from_date))
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "from_date không hợp lệ (YYYY-MM-DD)")
    if to_date:
        try:
            stmt = stmt.where(QuyDNGiaoDich.ngay <= date.fromisoformat(to_date))
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "to_date không hợp lệ (YYYY-MM-DD)")
    if loai:
        if loai not in ("thu", "chi"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "loai phải 'thu' hoặc 'chi'")
        stmt = stmt.where(QuyDNGiaoDich.loai == loai)

    stmt = stmt.order_by(QuyDNGiaoDich.ngay.desc(), QuyDNGiaoDich.id.desc()).limit(limit).offset(offset)
    items = db.execute(stmt).scalars().all()
    # `created_by` lưu username — tra tên một lượt cho cả trang, gắn THÊM `created_by_ten`.
    ten = ten_nv(db, [g.created_by for g in items]) if items else {}

    # Tổng thu / chi tổng quỹ (không filter theo from/to/loai — để header header summary)
    tong_thu = db.execute(
        select(func.coalesce(func.sum(QuyDNGiaoDich.so_tien), 0))
        .where(QuyDNGiaoDich.quy_id == quy_id, QuyDNGiaoDich.loai == "thu")
    ).scalar() or 0
    tong_chi = db.execute(
        select(func.coalesce(func.sum(QuyDNGiaoDich.so_tien), 0))
        .where(QuyDNGiaoDich.quy_id == quy_id, QuyDNGiaoDich.loai == "chi")
    ).scalar() or 0

    return {
        "quy_id": quy_id,
        "ten_quy": quy.ten_quy,
        "so_du": float(quy.so_du or 0),
        "tong_thu": float(tong_thu),
        "tong_chi": float(tong_chi),
        "items": [{**_serialize_gd(g), "created_by_ten": ten.get(g.created_by, g.created_by) or ""} for g in items],
        "can_admin": _can_admin(user),
    }


@giao_dich_router.get("/{quy_id}/so-du")
def get_so_du_quy(
    quy_id: int,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Số dư hiện tại + ngày giao dịch gần nhất."""
    quy = db.get(QuyDN, quy_id)
    if not quy:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quỹ không tồn tại")

    last_ngay = db.execute(
        select(func.max(QuyDNGiaoDich.ngay))
        .where(QuyDNGiaoDich.quy_id == quy_id)
    ).scalar()

    return {
        "quy_id": quy.id,
        "ten_quy": quy.ten_quy,
        "so_du": float(quy.so_du or 0),
        "last_giao_dich_ngay": last_ngay.isoformat() if last_ngay else None,
    }


@giao_dich_router.post("/{quy_id}/recalc")
def recalc_quy(
    quy_id: int,
    request: Request,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Recalc so_du = SUM(thu) - SUM(chi). Self-healing nếu lệch (admin/CEO)."""
    if not _can_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ admin/CEO được recalc")
    quy = db.get(QuyDN, quy_id)
    if not quy:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quỹ không tồn tại")

    so_du_cu = float(quy.so_du or 0)
    new_so_du = recalc_so_du(db, quy_id)
    db.commit()
    log_action(
        db, app="ketoan", action="quy_recalc",
        user=user, request=request, resource=f"quy:{quy_id}",
        payload={"so_du_cu": so_du_cu, "so_du_moi": float(new_so_du)},
    )
    return {
        "quy_id": quy_id,
        "ten_quy": quy.ten_quy,
        "so_du_cu": so_du_cu,
        "so_du_moi": float(new_so_du),
        "delta": float(new_so_du) - so_du_cu,
    }


@giao_dich_router.delete("/giao-dich/{gd_id}")
def void_giao_dich_quy(
    gd_id: int,
    request: Request,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Void 1 giao dịch quỹ + đảo ngược so_du. (admin/CEO)"""
    if not _can_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ admin/CEO được void giao dịch")
    payload = void_giao_dich(db, gd_id, by_user=user.username)
    db.commit()
    log_action(
        db, app="ketoan", action="quy_void_gd",
        user=user, request=request, resource=f"quy_dn_giao_dich:{gd_id}",
        payload=payload,
    )
    return payload
