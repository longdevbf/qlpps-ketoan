"""Kế Toán xác nhận cọc — bước cuối trước khi đơn lên Mua Hàng.

Luồng: KD gửi → Manager approve (kt_pending) → KT approve tại đây → push MH.
KT từ chối → kt_rejected ("Chưa Về Tiền") → KD + Manager thấy.
"""
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.auth import JWTPayload, require_app
from shared.audit import log_action
from shared.db import get_db
from shared.events import emit_event

router = APIRouter()
_AUTH = Depends(require_app("ketoan"))


# ── Schema ──────────────────────────────────────────────────────────

class KTDuyetBody(BaseModel):
    action: str = Field(..., pattern="^(approved|rejected)$")
    kt_ghi_chu: Optional[str] = None
    # KT chọn tài khoản thực nhận cọc lúc duyệt (VD 'ACB Hộ Kinh Doanh',
    # 'BIDV - Công ty', 'Tiền Mặt', 'VPB'). Nếu có → ghi đè coc_ngan_hang để
    # sổ quỹ book đúng TK (đơn KD chọn 'Chuyển khoản' nhưng chưa chọn NH cụ thể).
    tai_khoan: Optional[str] = None


# ── Helper: lazy import Quote từ baogia (cross-app) ─────────────────

def _get_quote(db: Session, qid: int):
    from baogia.app.models import Quote
    q = db.get(Quote, qid)
    if not q:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Đơn không tồn tại")
    return q


def _fmt_vnd(n) -> str:
    if not n:
        return "—"
    return f"{int(n):,}đ".replace(",", ".")


# ── Tự ghi cọc → doanh thu + sổ quỹ khi KT duyệt (anh Quang 2026-07-08) ──────
_COC_TK_MAP = {"tien_mat": "Tiền Mặt", "chuyen_khoan": "ACB Hộ Kinh Doanh"}


def _quote_nhom_master(db: Session, quote_id) -> Optional[str]:
    """Loại đơn theo SP CHÍNH: 'Đồ Mây' nếu đơn có SP mây, else 'Đồ Gỗ', None nếu
    chỉ toàn phụ kiện/không khớp. Tra `shared.products.nhom_master` theo product_type
    (match label/ten_sp). Phụ kiện/dịch vụ (nhom_master khác) bỏ qua."""
    if not quote_id:
        return None
    from sqlalchemy import text as _text
    try:
        rows = db.execute(_text("""
            SELECT DISTINCT p.nhom_master
            FROM baogia.quote_items qi
            JOIN shared.products p
              ON lower(trim(p.label))  = lower(trim(qi.product_type))
              OR lower(trim(p.ten_sp)) = lower(trim(qi.product_type))
            WHERE qi.quote_id = :qid AND p.nhom_master IN ('Đồ Gỗ', 'Đồ Mây')
        """), {"qid": quote_id}).scalars().all()
    except Exception:
        return None
    s = set(rows)
    if "Đồ Mây" in s:
        return "Đồ Mây"
    if "Đồ Gỗ" in s:
        return "Đồ Gỗ"
    return None


def _sync_coc_to_soquy(db: Session, quote, username: str) -> None:
    """KT duyệt cọc → tự tạo doanh thu 'Đặt cọc' → sổ quỹ thu.

    - Idempotent: đơn đã có doanh thu cọc (ma_don + loai_thanh_toan 'Đặt cọc')
      → bỏ qua (không double với đơn KT đã nhập tay trước đây).
    - Tài khoản: ưu tiên quote.coc_ngan_hang; fallback theo coc_hinh_thuc
      (tien_mat→Tiền Mặt, chuyen_khoan→ACB); mặc định Tiền Mặt. KT sửa lại TK
      trong sổ quỹ nếu cần.
    - Fail-soft: lỗi thì rollback, KHÔNG chặn việc duyệt cọc.
    """
    from datetime import date as _date_cls
    from decimal import Decimal

    from ..models import DoanhThu
    from ..services.so_quy_auto import sync_so_quy_from_doanh_thu

    try:
        so_tien = quote.coc_so_tien or getattr(quote, "deposit", None)
        if not so_tien or float(so_tien) <= 0:
            return
        qnum = quote.quote_number or ""
        existed = db.execute(
            select(DoanhThu)
            .where(DoanhThu.ma_don == qnum, DoanhThu.loai_thanh_toan.ilike("%cọc%"))
            .limit(1)
        ).scalar_one_or_none()
        if existed:
            return  # đã ghi cọc — bỏ qua

        tk = getattr(quote, "coc_ngan_hang", None) or _COC_TK_MAP.get(
            (quote.coc_hinh_thuc or "").strip().lower(), "Tiền Mặt"
        )
        # Loại đơn Mây/Gỗ theo SP CHÍNH của đơn (Anh Quang 2026-07-09) → auto điền
        # đúng loại doanh thu trên sổ quỹ. Phụ kiện/dịch vụ trung lập → bỏ qua.
        nm = _quote_nhom_master(db, getattr(quote, "id", None)) or ""
        loai_dt = "Doanh thu đồ mây" if nm == "Đồ Mây" else "Doanh thu đồ gỗ lẻ"

        dt = DoanhThu(
            ngay=quote.coc_ngay or _date_cls.today(),
            loai=loai_dt,
            so_tien=Decimal(str(so_tien)),
            nv_kinh_doanh=quote.salesperson or None,
            ma_don=qnum,
            ngan_hang=tk,
            loai_thanh_toan="Đặt cọc",
            mo_ta=f"Cọc đơn {qnum} - {quote.customer_name or ''}".strip(),
            ghi_chu="Tự động khi KT duyệt cọc",
            created_by=username,
        )
        db.add(dt)
        db.flush()
        sync_so_quy_from_doanh_thu(db, dt)
        db.commit()
    except Exception:
        db.rollback()
        import logging
        logging.getLogger(__name__).warning(
            "sync_coc_to_soquy failed qid=%s", getattr(quote, "id", None), exc_info=True
        )


# ── API: List đơn chờ KT ─────────────────────────────────────────────

@router.get("/api/kt-duyet/list")
def list_kt_pending(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Trả danh sách đơn duyet_status=kt_pending (chờ KT xác nhận).
    Cũng trả kt_rejected để KT theo dõi.
    """
    from baogia.app.models import Quote
    rows = db.execute(
        select(Quote)
        .where(Quote.duyet_status.in_(["kt_pending", "kt_rejected"]))
        .order_by(Quote.created_at.desc())
    ).scalars().all()

    # Chênh giá NV bán vs hệ thống (Anh Quang 2026-07-13) — bulk theo quote_id.
    from sqlalchemy import text as _text
    _ids = [q.id for q in rows]
    _diff = {}
    if _ids:
        try:
            for r in db.execute(_text("""
                SELECT quote_id,
                       SUM(COALESCE(don_gia_tinh,0) * COALESCE(so_luong,1)) AS ban,
                       SUM(COALESCE(don_gia_he_thong, don_gia_tinh, 0) * COALESCE(so_luong,1)) AS ht,
                       COUNT(*) FILTER (WHERE don_gia_he_thong IS NOT NULL
                             AND ABS(COALESCE(don_gia_tinh,0) - don_gia_he_thong) > 0.5) AS n
                FROM baogia.quote_items WHERE quote_id = ANY(:ids) GROUP BY quote_id
            """), {"ids": _ids}).all():
                _diff[r[0]] = (float(r[1] or 0), float(r[2] or 0), int(r[3] or 0))
        except Exception:
            _diff = {}

    def _dg(qid):
        ban, ht, n = _diff.get(qid, (0.0, 0.0, 0))
        return {"gia_ban_total": ban, "gia_he_thong_total": ht,
                "gia_chenh": round(ban - ht, 2), "gia_chenh_n": n}

    return [
        {
            "id": q.id,
            "quote_number": q.quote_number or "",
            "customer_name": q.customer_name or "",
            "customer_phone": q.customer_phone or "",
            "salesperson": q.salesperson or "",
            "tong_don": float(q.tong_don) if q.tong_don else None,
            "duyet_status": q.duyet_status,
            "duyet_boi": q.duyet_boi or "",
            "duyet_luc": q.duyet_luc.isoformat() if q.duyet_luc else "",
            # Cọc hiệu lực: ưu tiên coc_so_tien (KD ghi cọc chi tiết), fallback
            # `deposit` (Tiền cọc form) để KT KHÔNG bỏ sót đơn có cọc nhập ở ô
            # deposit (Anh Quang 2026-07-08). coc_tu_deposit=True → chưa có hình thức.
            "coc_so_tien": (
                float(q.coc_so_tien) if q.coc_so_tien
                else (float(q.deposit) if q.deposit else None)
            ),
            "coc_tu_deposit": bool((not q.coc_so_tien) and q.deposit),
            "coc_ngay": q.coc_ngay.isoformat() if q.coc_ngay else None,
            "coc_hinh_thuc": q.coc_hinh_thuc or "",
            "coc_ngan_hang": getattr(q, "coc_ngan_hang", None) or "",
            "coc_ghi_chu": q.coc_ghi_chu or "",
            "kt_ghi_chu": q.kt_ghi_chu or "",
            "kt_duyet_boi": q.kt_duyet_boi or "",
            "kt_duyet_luc": q.kt_duyet_luc.isoformat() if q.kt_duyet_luc else "",
            "created_at": q.created_at.isoformat() if q.created_at else "",
            **_dg(q.id),
        }
        for q in rows
    ]


# ── API: KT xác nhận / từ chối ───────────────────────────────────────

@router.post("/api/kt-duyet/{qid}")
def kt_duyet(
    qid: int,
    body: KTDuyetBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """KT approve → approved + push MH. KT reject → kt_rejected ('Chưa Về Tiền')."""
    quote = _get_quote(db, qid)

    if (quote.duyet_status or "") != "kt_pending":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Đơn không ở trạng thái chờ KT (hiện: {quote.duyet_status})",
        )

    quote.kt_duyet_boi = user.username
    quote.kt_duyet_luc = datetime.now(tz=timezone.utc)
    if body.kt_ghi_chu is not None:
        quote.kt_ghi_chu = body.kt_ghi_chu

    if body.action == "approved":
        quote.duyet_status = "approved"
        quote.status = "approved"
        # KT chốt TK thực nhận cọc → lưu vào coc_ngan_hang (đơn 'Chuyển khoản'
        # nhưng KD chưa chọn NH cụ thể) để sổ quỹ book đúng tài khoản.
        _tk = (body.tai_khoan or "").strip()
        if _tk:
            try:
                quote.coc_ngan_hang = _tk
            except Exception:
                pass
    else:
        quote.duyet_status = "kt_rejected"
        quote.status = "sent"

    db.commit()
    db.refresh(quote)

    if body.action == "approved":
        emit_event("quote:duyet", {
            "id": quote.id,
            "quote_number": quote.quote_number,
            "action": "approved",
            "duyet_boi": user.username,
        })
        # Cọc chạy thẳng lên sổ quỹ (idempotent, fail-soft)
        _sync_coc_to_soquy(db, quote, user.username)

    log_action(
        db, app="ketoan", action=f"kt_duyet_{body.action}", user=user, request=request,
        resource=f"quote:{qid}",
        payload={"kt_ghi_chu": body.kt_ghi_chu, "quote_number": quote.quote_number},
    )

    try:
        from shared.services.notify import notify_quote_duyet
        notify_quote_duyet(db, quote, action=f"kt_{body.action}", by=user.username)
        db.commit()
    except Exception:
        db.rollback()

    return {
        "ok": True,
        "duyet_status": quote.duyet_status,
        "quote_number": quote.quote_number,
    }


# ── HTML page ────────────────────────────────────────────────────────

@router.get("/kt-duyet", response_class=HTMLResponse, name="kt_duyet_page")
def kt_duyet_page(request: Request):
    """Trang KT xác nhận cọc — render từ template riêng."""
    from pathlib import Path
    from fastapi.templating import Jinja2Templates
    from shared.templates import setup_jinja2, user_ctx
    from shared.auth.jwt import verify_jwt

    token = request.cookies.get("access_token")
    if not token:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/login")
    try:
        jwt_user = verify_jwt(token)
    except Exception:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/login")

    _tpl_dir = Path(__file__).resolve().parent.parent.parent / "templates"
    templates = Jinja2Templates(directory=str(_tpl_dir))
    setup_jinja2(templates)

    actor = user_ctx(jwt_user)
    return templates.TemplateResponse(
        "kt_duyet.html",
        {"request": request, "user": actor, "actor": actor},
    )
