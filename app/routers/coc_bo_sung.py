"""Kế Toán duyệt CỌC BỔ SUNG (lần 2, 3, …) từ báo giá.

Anh Quang 2026-08-24. NV KD báo cọc bổ sung bên baogia (baogia.quote_deposits,
trang_thai='cho_duyet'). KT duyệt TỪNG lần ở đây → mỗi lần tạo 1 DoanhThu 'Đặt
cọc' → sổ quỹ THU riêng (ref DT-{id} duy nhất). "Tổng đã cọc" (= SUM sổ quỹ thu
theo ma_don) TỰ cộng dồn. Chống chi/thu 2 lần: chỉ duyệt khi trang_thai='cho_duyet'
+ chưa có doanh_thu_id.
"""
from __future__ import annotations

from datetime import date as _date_cls, datetime, timezone
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text as _sqltext
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload, require_app
from shared.db import get_db
from shared.templates import _lookup_user_info

router = APIRouter()
_AUTH = Depends(require_app("ketoan"))

_COC_TK_MAP = {"tien_mat": "Tiền Mặt", "chuyen_khoan": "ACB Hộ Kinh Doanh"}
# KT/CEO mới được duyệt cọc bổ sung
_APPROVE_ROLES = ("manager", "admin", "ceo", "assistant_ceo")


class DuyetBody(BaseModel):
    action: str = Field("duyet", pattern="^(duyet|tu_choi)$")
    tai_khoan: Optional[str] = None       # TK thực nhận (KT chốt)
    ghi_chu: Optional[str] = None


def _row_dict(d, q=None) -> dict:
    out = {
        "id": d.id, "quote_id": d.quote_id, "quote_number": d.quote_number,
        "lan": d.lan, "so_tien": float(d.so_tien or 0),
        "ngan_hang": d.ngan_hang, "hinh_thuc": d.hinh_thuc,
        "ngay": d.ngay.isoformat() if d.ngay else None,
        "ghi_chu": d.ghi_chu, "trang_thai": d.trang_thai,
        "nguoi_tao": d.nguoi_tao,
        "kt_duyet_boi": d.kt_duyet_boi,
        "kt_duyet_luc": d.kt_duyet_luc.isoformat() if d.kt_duyet_luc else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }
    if q is not None:
        out["customer_name"] = getattr(q, "customer_name", None)
        out["salesperson"] = getattr(q, "salesperson", None)
        out["tong_don"] = float(getattr(q, "tong_don", 0) or 0)
    return out


@router.get("/api/coc-bo-sung/pending")
def pending(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
) -> dict:
    """Các lần cọc bổ sung đang chờ KT duyệt (cũ nhất trước)."""
    from baogia.app.models import QuoteDeposit, Quote  # lazy cross-app

    rows = db.execute(
        select(QuoteDeposit)
        .where(QuoteDeposit.trang_thai == "cho_duyet")
        .order_by(QuoteDeposit.created_at.asc())
    ).scalars().all()
    items, tong = [], 0.0
    for d in rows:
        q = db.get(Quote, d.quote_id)
        items.append(_row_dict(d, q))
        tong += float(d.so_tien or 0)
    return {"items": items, "count": len(items), "tong_tien": tong}


@router.post("/api/coc-bo-sung/{did}/duyet")
def duyet(
    did: int,
    body: DuyetBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
) -> dict:
    """KT duyệt / từ chối 1 lần cọc bổ sung.

    Duyệt → tạo DoanhThu 'Đặt cọc' + sổ quỹ thu (theo NGÀY cọc NV nhập), gắn
    doanh_thu_id. Idempotent: chỉ chạy khi trang_thai='cho_duyet'.
    """
    if user.role not in _APPROVE_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ Kế Toán/CEO được duyệt cọc")

    from baogia.app.models import QuoteDeposit, Quote  # lazy cross-app
    from ..models import DoanhThu
    from ..services.so_quy_auto import sync_so_quy_from_doanh_thu

    d = db.get(QuoteDeposit, did)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không thấy lần cọc bổ sung")
    if d.trang_thai != "cho_duyet":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Lần cọc này đã được xử lý (trạng thái: {d.trang_thai}) — không duyệt lại.",
        )

    q = db.get(Quote, d.quote_id)

    # Từ chối — chỉ đổi trạng thái
    if body.action == "tu_choi":
        d.trang_thai = "tu_choi"
        d.kt_duyet_boi = user.username
        d.kt_duyet_luc = datetime.now(tz=timezone.utc)
        if body.ghi_chu:
            d.kt_ghi_chu = body.ghi_chu
        db.commit()
        _notify_nv(db, d, q, ok=False, by=user.username)
        return {"ok": True, "id": did, "trang_thai": "tu_choi"}

    # Duyệt — tạo doanh thu 'Đặt cọc' → sổ quỹ (atomic)
    tk = (body.tai_khoan or "").strip() or _COC_TK_MAP.get(
        (d.hinh_thuc or "").strip().lower(), "Tiền Mặt"
    )
    # Loại doanh thu theo SP chính (Mây/Gỗ) — khớp lần 1
    try:
        from .kt_duyet import _quote_nhom_master
        nm = _quote_nhom_master(db, d.quote_id) or ""
    except Exception:
        nm = ""
    loai_dt = "Doanh thu đồ mây" if nm == "Đồ Mây" else "Doanh thu đồ gỗ lẻ"
    ngay_ghi = d.ngay or _date_cls.today()

    try:
        dt = DoanhThu(
            ngay=ngay_ghi,
            loai=loai_dt,
            so_tien=Decimal(str(d.so_tien or 0)),
            nv_kinh_doanh=(getattr(q, "salesperson", None) if q else None),
            ma_don=d.quote_number,
            ngan_hang=tk,
            loai_thanh_toan="Đặt cọc",
            mo_ta=f"Cọc bổ sung lần {d.lan} đơn {d.quote_number} - {getattr(q,'customer_name','') or ''}".strip(),
            ghi_chu=f"Tự động khi KT duyệt cọc bổ sung (lần {d.lan})",
            created_by=user.username,
        )
        db.add(dt)
        db.flush()                       # có dt.id
        sync_so_quy_from_doanh_thu(db, dt)   # → sổ quỹ thu ref DT-{id}
        d.trang_thai = "duyet"
        d.kt_duyet_boi = user.username
        d.kt_duyet_luc = datetime.now(tz=timezone.utc)
        d.ngan_hang = tk
        d.doanh_thu_id = dt.id
        if body.ghi_chu:
            d.kt_ghi_chu = body.ghi_chu
        db.commit()
        db.refresh(d)
    except Exception as ex:
        db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Duyệt cọc thất bại — sổ quỹ lỗi: {ex}"
        )

    if not d.doanh_thu_id:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Duyệt cọc chưa ghi được doanh thu")

    # Gắn ma_don cho các dòng sổ quỹ thu là CỌC của đơn này (cọc lần 1 + các lần
    # bổ sung) → "Tổng đã cọc" bên baogia (SUM so_quy thu theo ma_don) TỰ cộng dồn.
    # CHỈ dòng cọc ('Đặt cọc') — KHÔNG đụng dòng thanh toán/thu khác (tránh thổi
    # phồng "đã cọc"). Bridge mặc định không set ma_don nên phải vá; targeted theo
    # đơn có cọc bổ sung, fail-soft.
    try:
        db.execute(_sqltext("""
            UPDATE ketoan.so_quy sq SET ma_don = dt.ma_don
            FROM ketoan.doanh_thu dt
            WHERE sq.lien_quan = 'doanh_thu' AND sq.ref_id = 'DT-' || dt.id
              AND dt.ma_don = :qnum AND dt.loai_thanh_toan ILIKE '%cọc%'
              AND sq.ma_don IS DISTINCT FROM dt.ma_don
        """), {"qnum": d.quote_number})
        db.commit()
    except Exception:
        db.rollback()

    log_action(
        db, app="ketoan", action="coc_bo_sung_duyet", user=user, request=request,
        resource=f"quote_deposit:{did}",
        payload={"quote_number": d.quote_number, "lan": d.lan,
                 "so_tien": float(d.so_tien or 0), "tai_khoan": tk},
    )
    _notify_nv(db, d, q, ok=True, by=user.username)

    # Báo "đã duyệt tiền" (cọc bổ sung) lên nhóm "Kinh Doanh - Kế Toán" (fail-soft).
    try:
        from shared.services.chat_post import post_to_group
        # Tên thật thay cho mã NV — xem ghi chú ở kt_duyet.py
        _kt_ten = _lookup_user_info(user.username)[0] or user.username
        _msg = (
            f"✅ Kế Toán {_kt_ten} đã duyệt cọc bổ sung lần {d.lan} "
            f"đơn {d.quote_number} — {int(float(d.so_tien or 0)):,}đ đã vào sổ quỹ. "
            f"KH {getattr(q, 'customer_name', '') or ''}."
        )
        post_to_group(db, content=_msg)
    except Exception:
        pass

    return {"ok": True, "id": did, "trang_thai": "duyet", "doanh_thu_id": d.doanh_thu_id}


def _notify_nv(db, d, q, *, ok: bool, by: str) -> None:
    """Báo NV tạo kết quả duyệt cọc bổ sung (fail-soft)."""
    try:
        from shared.services.notify import notify
        target = getattr(d, "nguoi_tao", None)
        if not target:
            return
        st = int(float(d.so_tien or 0))
        if ok:
            notify(
                db, target=target, source_app="baogia",
                event_type="coc_bs:approved",
                title=f"[Cọc bổ sung] KT đã duyệt — đơn {d.quote_number}",
                message=f"Lần {d.lan}: {st:,}đ đã vào sổ quỹ",
                ref_type="quote", ref_id=d.quote_number,
                url="https://baogia.qlpps.com/", severity="success", created_by=by,
            )
        else:
            notify(
                db, target=target, source_app="baogia",
                event_type="coc_bs:rejected",
                title=f"[Cọc bổ sung] KT từ chối — đơn {d.quote_number}",
                message=f"Lần {d.lan}: {st:,}đ — {d.kt_ghi_chu or 'không rõ lý do'}",
                ref_type="quote", ref_id=d.quote_number,
                url="https://baogia.qlpps.com/", severity="warning", created_by=by,
            )
        db.commit()
    except Exception:
        db.rollback()
