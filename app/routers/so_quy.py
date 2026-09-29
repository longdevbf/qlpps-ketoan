"""SoQuy API — auto-sync từ DoanhThu/ChiPhi/CongNo + chuyển nội bộ.

Anh chốt 2026-04-29: bỏ nhập tay sổ quỹ. Mọi entry sinh tự động qua hook
`so_quy_auto.py` từ 3 module nguồn. Riêng "chuyển nội bộ" giữa 2 TK có
endpoint riêng `POST /chuyen-noi-bo` (idempotent qua ref_id).

Manual CRUD vẫn giữ nhưng GATE chỉ admin/ceo/assistant_ceo (bỏ `manager`/`kt`).
"""
from datetime import date as date_cls, timedelta
from decimal import Decimal
from typing import Annotated, Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import SoQuy, TaiKhoanNH
from ..schemas import SoQuyCreate, SoQuyUpdate, SoQuyOut
from ..services.so_quy_auto import so_du_truoc_ngay
from ._deps import require_ketoan_user, require_ceo_thuchi


router = APIRouter()
_AUTH = Depends(require_ketoan_user)
_CEO_EDIT = Depends(require_ceo_thuchi)  # sửa/xoá lệnh thu chi → chỉ CEO
# Kế Toán (`kt`) + Manager cũng được CRUD sổ quỹ tay (xoá entry orphan, sửa
# số phụ phí phát sinh ngoài luồng). admin/ceo/assistant_ceo giữ nguyên.
_ADMIN_ROLES = {"admin", "ceo", "assistant_ceo", "manager", "kt"}


def _require_admin(user: JWTPayload) -> None:
    """Manual CRUD sổ quỹ — admin/ceo/assistant_ceo/manager/kt được phép.
    Role thấp khác (kd/mkt/...) bị chặn vì không phải đối tượng dùng app này."""
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Sổ quỹ tự động sync từ Doanh Thu/Chi Phí/Công Nợ. "
            f"Role {user.role!r} không có quyền sửa tay.",
        )


def _lookup_nv_ten(db: Session, nv_id: Optional[int]) -> Optional[str]:
    """Auto-lookup ho_ten từ hcns.employees.

    hcns.employees PK = ma_nv (string vd 'NV26015'). Convert int 26015
    → 'NV%26015' để match qua ILIKE / suffix-match. Fail-soft trả None.
    """
    if not nv_id:
        return None
    try:
        # Match: ma_nv chứa cùng dãy số (vd 26015 → 'NV26015' / 'NV-26015' / 'NV_26015')
        row = db.execute(
            text(
                "SELECT ho_ten FROM hcns.employees "
                "WHERE regexp_replace(ma_nv, '\\D', '', 'g') = :digits "
                "LIMIT 1"
            ),
            {"digits": str(nv_id)},
        ).first()
        return row[0] if row else None
    except (ProgrammingError, OperationalError):
        db.rollback()
        return None


def _parse_thang(thang: Optional[str]) -> tuple[date_cls, date_cls]:
    """Trả (start_of_month, start_of_next_month). Default = current month."""
    today = date_cls.today()
    if not thang:
        y, m = today.year, today.month
    else:
        try:
            y_str, m_str = thang.split("-", 1)
            y, m = int(y_str), int(m_str)
        except (ValueError, AttributeError):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Tham số thang phải dạng YYYY-MM",
            )
    if not (1 <= m <= 12):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Tham số thang: tháng phải 1..12"
        )
    sm = date_cls(y, m, 1)
    em = date_cls(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
    return sm, em


@router.get("/summary")
def so_quy_summary(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    thang: Optional[str] = Query(None, description="YYYY-MM, default = current"),
    tu_ngay: Optional[date_cls] = Query(None, description="Kỳ tuỳ ý: từ ngày (gồm)"),
    den_ngay: Optional[date_cls] = Query(None, description="Kỳ tuỳ ý: đến ngày (gồm)"),
) -> dict[str, Any]:
    """Số dư từng tài khoản theo tháng (port từ V1 `/api/so-quy/summary`).

    Logic:
        so_du_dau_thang = tai_khoan_nh.so_du_dau + sum(SoQuy.thu - chi WHERE ngay < sm)
        thu = sum(SoQuy.so_tien WHERE loai='thu' AND sm <= ngay < em)
        chi = sum(SoQuy.so_tien WHERE loai='chi' AND sm <= ngay < em)
        so_du_cuoi = so_du_dau_thang + thu - chi

    Có `tu_ngay` + `den_ngay` (2026-09-25, màn Ngân hàng/Sổ quỹ lọc theo kỳ bất kỳ) →
    bỏ qua `thang`, tính trên [tu_ngay, den_ngay] (gồm 2 đầu); "so_du_dau_thang" khi
    đó là số dư NGAY TRƯỚC tu_ngay (`so_quy_auto.so_du_truoc_ngay`, cùng thuật toán neo).
    Không truyền → hành vi cũ theo tháng giữ nguyên (màn cũ /app#so-quy vẫn dùng).
    """
    if tu_ngay and den_ngay:
        if den_ngay < tu_ngay:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "den_ngay phải ≥ tu_ngay")
        sm, em = tu_ngay, den_ngay + timedelta(days=1)
    else:
        sm, em = _parse_thang(thang)

    tks = db.execute(
        select(TaiKhoanNH.id, TaiKhoanNH.ten_tk, TaiKhoanNH.so_du_dau, TaiKhoanNH.loai)
        .where(TaiKhoanNH.active.is_(True))
        .order_by(TaiKhoanNH.ten_tk)
    ).all()

    items: list[dict[str, Any]] = []
    tong_dau = tong_thu = tong_chi = tong_cuoi = Decimal("0")

    for tk in tks:
        # Anh Quang 2026-06-05: Số dư cuối kỳ tháng (X-1) = đầu kỳ tháng X — liên tục.
        # Thuật toán neo (anchor SoDuDauKy, forward/reverse/fallback) dùng chung với
        # màn Ngân Hàng qua so_quy_auto.so_du_truoc_ngay (= so_du_dau_ky khi `sm` là
        # ngày 1) — tách ra 2026-09-25 để 2 màn không tính lệch nhau khi lọc theo kỳ.
        so_du_dau_thang = so_du_truoc_ngay(db, tk.id, tk.ten_tk, sm)

        # Trong tháng
        thu_thang = db.scalar(
            select(func.coalesce(func.sum(SoQuy.so_tien), 0)).where(
                SoQuy.tai_khoan == tk.ten_tk,
                SoQuy.loai == "thu",
                SoQuy.ngay >= sm,
                SoQuy.ngay < em,
            )
        ) or Decimal("0")
        chi_thang = db.scalar(
            select(func.coalesce(func.sum(SoQuy.so_tien), 0)).where(
                SoQuy.tai_khoan == tk.ten_tk,
                SoQuy.loai == "chi",
                SoQuy.ngay >= sm,
                SoQuy.ngay < em,
            )
        ) or Decimal("0")
        thu_thang = Decimal(thu_thang)
        chi_thang = Decimal(chi_thang)
        so_du_cuoi = so_du_dau_thang + thu_thang - chi_thang

        items.append({
            "tai_khoan_id": tk.id,
            "ten_tk": tk.ten_tk,
            "loai": tk.loai,
            "so_du_dau_thang": str(so_du_dau_thang),
            "thu": str(thu_thang),
            "chi": str(chi_thang),
            "so_du_cuoi": str(so_du_cuoi),
        })
        tong_dau += so_du_dau_thang
        tong_thu += thu_thang
        tong_chi += chi_thang
        tong_cuoi += so_du_cuoi

    return {
        "thang": f"{sm.year}-{sm.month:02d}",
        "tu_ngay": sm.isoformat(),
        "den_ngay": em.isoformat(),  # exclusive — start of next month
        "items": items,
        "tong": {
            "so_du_dau_thang": str(tong_dau),
            "thu": str(tong_thu),
            "chi": str(tong_chi),
            "so_du_cuoi": str(tong_cuoi),
        },
    }


@router.get("", response_model=list[SoQuyOut])
def list_so_quy(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu_ngay: Optional[date_cls] = Query(None),
    den_ngay: Optional[date_cls] = Query(None),
    thang: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    loai: Optional[str] = Query(None, pattern="^(thu|chi)$"),
    tai_khoan: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
    offset: int = 0,
):
    stmt = select(SoQuy).order_by(SoQuy.ngay.desc(), SoQuy.id.desc())
    # Filter theo `thang=YYYY-MM` (FE đang gửi param này) — ưu tiên hơn tu/den_ngay.
    # Trước đây bị ignore → widget "Chi Tiết Giao Dịch" trả cả lịch sử all-time
    # thay vì chỉ tháng được chọn. Fix 27/05.
    if thang:
        sm, em = _parse_thang(thang)
        stmt = stmt.where(SoQuy.ngay >= sm).where(SoQuy.ngay < em)
    else:
        if tu_ngay:
            stmt = stmt.where(SoQuy.ngay >= tu_ngay)
        if den_ngay:
            stmt = stmt.where(SoQuy.ngay <= den_ngay)
    if loai:
        stmt = stmt.where(SoQuy.loai == loai)
    if tai_khoan:
        stmt = stmt.where(SoQuy.tai_khoan == tai_khoan)
    stmt = stmt.limit(limit).offset(offset)
    return db.execute(stmt).scalars().all()


@router.post("", response_model=SoQuyOut, status_code=status.HTTP_201_CREATED)
def create_so_quy(
    body: SoQuyCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    _require_admin(user)
    fields = body.model_dump(exclude_unset=True)
    # CHẶN chi làm số dư TK âm (anh Quang 2026-08-27)
    if (fields.get("loai") or "").lower() == "chi":
        from ..services.so_quy_auto import assert_du_chi
        assert_du_chi(db, fields.get("tai_khoan"), fields.get("so_tien"))
    # Issue 1 — auto-lookup nhan_vien_ten nếu chỉ truyền nhan_vien_id
    nv_id = fields.get("nhan_vien_id")
    if nv_id and not (fields.get("nhan_vien_ten") or "").strip():
        nv_ten = _lookup_nv_ten(db, nv_id)
        if nv_ten:
            fields["nhan_vien_ten"] = nv_ten
    obj = SoQuy(**fields, created_by=user.username)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="create_so_quy", user=user, request=request,
        resource=f"so_quy:{obj.id}",
        payload={"ngay": str(obj.ngay), "loai": obj.loai, "so_tien": str(obj.so_tien)},
    )
    return obj


@router.get("/{rid}", response_model=SoQuyOut)
def get_so_quy(
    rid: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(SoQuy, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SoQuy không tồn tại")
    return obj


@router.put("/{rid}", response_model=SoQuyOut)
def update_so_quy(
    rid: int,
    body: SoQuyUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _CEO_EDIT],
):
    obj = db.get(SoQuy, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SoQuy không tồn tại")
    fields = body.model_dump(exclude_unset=True)
    # Issue 1 — re-lookup nhan_vien_ten khi đổi nhan_vien_id mà không truyền tên
    if "nhan_vien_id" in fields and not (fields.get("nhan_vien_ten") or "").strip():
        nv_ten = _lookup_nv_ten(db, fields["nhan_vien_id"])
        if nv_ten:
            fields["nhan_vien_ten"] = nv_ten
    for k, v in fields.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="update_so_quy", user=user, request=request,
        resource=f"so_quy:{rid}", payload=fields,
    )
    return obj


@router.delete("/{rid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_so_quy(
    rid: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _CEO_EDIT],
):
    obj = db.get(SoQuy, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SoQuy không tồn tại")
    db.delete(obj)
    db.commit()
    log_action(
        db, app="ketoan", action="delete_so_quy", user=user, request=request,
        resource=f"so_quy:{rid}",
    )


# ───────────────────── Chuyển nội bộ giữa 2 TK ─────────────────────────

class ChuyenNoiBoIn(BaseModel):
    ngay: date_cls
    tu_tai_khoan: str       # tên TK rút (Chi)
    den_tai_khoan: str      # tên TK nạp (Thu)
    so_tien: float
    noi_dung: Optional[str] = ""
    ghi_chu: Optional[str] = ""
    ref_id: Optional[str] = None  # cho idempotent — client gen UUID


@router.post("/chuyen-noi-bo", status_code=status.HTTP_201_CREATED)
def chuyen_noi_bo(
    body: ChuyenNoiBoIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
) -> dict[str, Any]:
    """Chuyển tiền giữa 2 tài khoản — tạo 2 entry idempotent.

    - Chi từ `tu_tai_khoan` (loai='chi')
    - Thu vào `den_tai_khoan` (loai='thu')
    - Cùng `ref_id` để link 2 entry. Re-call cùng ref_id → no-op (trả entry cũ).
    """
    if body.tu_tai_khoan == body.den_tai_khoan:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "TK nguồn và TK đích phải khác nhau",
        )
    if body.so_tien <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Số tiền phải > 0")

    # CHẶN chuyển đi làm số dư TK nguồn âm (anh Quang 2026-08-27)
    from ..services.so_quy_auto import assert_du_chi
    assert_du_chi(db, body.tu_tai_khoan, body.so_tien)

    ref_id = (body.ref_id or f"chuyennb_{uuid4().hex[:12]}")
    so_tien = Decimal(str(body.so_tien))

    # Idempotent: nếu đã có 2 entry cùng ref_id → trả luôn
    existing = db.execute(
        select(SoQuy).where(SoQuy.ref_id == ref_id)
    ).scalars().all()
    if existing:
        return {
            "ok": True,
            "ref_id": ref_id,
            "entries": [{"id": e.id, "loai": e.loai, "tk": e.tai_khoan, "so_tien": float(e.so_tien)} for e in existing],
            "idempotent_hit": True,
        }

    noi_dung_chi = (body.noi_dung or "").strip() or f"Chuyển sang {body.den_tai_khoan}"
    noi_dung_thu = (body.noi_dung or "").strip() or f"Nhận từ {body.tu_tai_khoan}"

    sq_chi = SoQuy(
        ngay=body.ngay,
        loai="chi",
        so_tien=so_tien,
        tai_khoan=body.tu_tai_khoan,
        noi_dung=noi_dung_chi,
        lien_quan="chuyen_noi_bo",
        phan_loai_cf="khac",
        ref_id=ref_id,
        ghi_chu=body.ghi_chu or None,
        created_by=user.username,
    )
    sq_thu = SoQuy(
        ngay=body.ngay,
        loai="thu",
        so_tien=so_tien,
        tai_khoan=body.den_tai_khoan,
        noi_dung=noi_dung_thu,
        lien_quan="chuyen_noi_bo",
        phan_loai_cf="khac",
        ref_id=ref_id,
        ghi_chu=body.ghi_chu or None,
        created_by=user.username,
    )
    db.add(sq_chi)
    db.add(sq_thu)
    db.commit()
    db.refresh(sq_chi)
    db.refresh(sq_thu)

    log_action(
        db, app="ketoan", action="so_quy_chuyen_noi_bo",
        user=user, request=request, resource=f"so_quy:{ref_id}",
        payload={
            "tu": body.tu_tai_khoan, "den": body.den_tai_khoan,
            "so_tien": float(so_tien),
        },
    )
    return {
        "ok": True,
        "ref_id": ref_id,
        "entries": [
            {"id": sq_chi.id, "loai": "chi", "tk": sq_chi.tai_khoan, "so_tien": float(sq_chi.so_tien)},
            {"id": sq_thu.id, "loai": "thu", "tk": sq_thu.tai_khoan, "so_tien": float(sq_thu.so_tien)},
        ],
        "idempotent_hit": False,
    }
