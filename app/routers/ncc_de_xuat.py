"""Kế Toán duyệt CẤP 1 cho "Đề xuất trả nợ NCC" của app Mua Hàng.

Source of truth: `muahang.congno` (loai='de_xuat_tra'). KT KHÔNG tạo bản sao —
đọc/ghi trực tiếp qua ORM (lazy import, cùng DB).

Luồng 2 cấp (mirror saleadmin.denghitt):
  NV Mua Hàng đề xuất (cho_duyet) → KT duyệt (ở đây) → kt_duyet → CEO duyệt cuối
  ở app Mua Hàng → duyet (+ bridge ketoan.so_quy).
  KT từ chối → kt_tu_choi (kết thúc).

Mounted KHÔNG prefix trong ketoan/app/main.py (paths đã full /api/ncc-de-xuat...).
"""
from datetime import date as _date, datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload, require_app
from shared.db import get_db
from shared.routers.duyet_chi import _ngay_ghi_so

from ..services.ban_sao_de_nghi import tu_choi_dntt_kem


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


class TuChoiTruocChiBody(BaseModel):
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
        "da_chi": bool(getattr(e, "da_chi", False)),
        "tai_khoan_chi": getattr(e, "tai_khoan_chi", None),
        "ngay_chi": e.ngay_chi.isoformat() if getattr(e, "ngay_chi", None) else None,
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
    da_chi: Optional[bool] = Query(None, description="lọc đã trả (True) — danh sách lệnh đã trả NCC"),
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
    if da_chi is not None:
        # da_chi=True → CHỈ các lệnh ĐÃ TRẢ NCC (mới nhất theo ngày chi)
        stmt = stmt.where(CongNo.da_chi.is_(True) if da_chi else CongNo.da_chi.isnot(True))
        if da_chi:
            stmt = stmt.order_by(None).order_by(CongNo.ngay_chi.desc().nullslast())
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
    out = {(tt or ""): n for tt, n in rows}
    # Đếm ĐÃ TRẢ (da_chi) cho tab "Đã trả"
    out["da_chi"] = db.execute(
        select(func.count(CongNo.id))
        .where(CongNo.loai == "de_xuat_tra", CongNo.da_chi.is_(True))
    ).scalar() or 0
    return out


# ── Công nợ NCC còn phải trả — nguồn cho màn mới /ketoan/de-xuat-ncc ─────────
# Cùng công thức với muahang GET /api/congno/summary (màn Công nợ NCC của Mua Hàng):
#   nợ = SUM(no_phai_tra) ; đã trả = SUM(de_xuat_tra ĐÃ CHI) ; còn nợ = max(0, nợ − đã trả) — tính THEO NCC.
# Khác một chỗ có chủ đích: "đang đề xuất" CHỈ tính đề xuất còn sống (cho_duyet / kt_duyet / duyet chưa chi);
# muahang cộng cả đề xuất đã bị TỪ CHỐI (không da_chi) vào dang_de_xuat → số "còn đề xuất được" bị thấp sai.
# Thực tế 100% đề xuất trả NCC hiện có đều KHÔNG gắn đơn (ref_order_id NULL — trả theo tổng NCC), nên "còn nợ
# từng đơn" chỉ tính được bằng cách trừ dần tiền đã trả / đang đề xuất vào đơn CŨ NHẤT trước (FIFO) — chỉ để
# gợi ý chọn; kiểm tra chặn vượt là theo TỔNG NCC.
_DX_SONG = ("cho_duyet", "kt_duyet", "duyet")
_SO = ("no_phai_tra", "da_tra", "dang_de_xuat", "con_no", "co_the_de_xuat")


def _tong_ncc(db: Session, ncc_id: Optional[str] = None) -> tuple[dict, list]:
    from decimal import Decimal
    from muahang.app.models import CongNo  # lazy
    stmt = select(CongNo)
    if ncc_id:
        stmt = stmt.where(CongNo.ncc_id == ncc_id)
    zero = Decimal("0")
    by: dict[str, dict] = {}
    no_rows = []
    for e in db.execute(stmt).scalars():
        if not e.ncc_id:
            continue
        v = by.setdefault(e.ncc_id, {"id": e.ncc_id, "ten": e.ncc_name or e.ncc_id,
                                     "no_phai_tra": zero, "da_tra": zero, "dang_de_xuat": zero})
        if e.ncc_name:
            v["ten"] = e.ncc_name
        st = e.so_tien or zero
        if e.loai == "no_phai_tra":
            v["no_phai_tra"] += st
            no_rows.append(e)
        elif e.loai == "de_xuat_tra":
            if getattr(e, "da_chi", False):
                v["da_tra"] += st
            elif (e.trang_thai or "") in _DX_SONG:
                v["dang_de_xuat"] += st
    for v in by.values():
        v["con_no"] = max(zero, v["no_phai_tra"] - v["da_tra"])
        v["co_the_de_xuat"] = max(zero, v["con_no"] - v["dang_de_xuat"])
    return by, no_rows


@router.get("/api/ncc-de-xuat/cong-no")
def cong_no_theo_ncc(
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """Danh sách NCC còn nợ (còn_nợ > 0), nợ nhiều nhất trước."""
    by, _ = _tong_ncc(db)
    rows = sorted((v for v in by.values() if v["con_no"] > 0), key=lambda v: v["con_no"], reverse=True)
    return [{**v, **{k: float(v[k]) for k in _SO}} for v in rows]


@router.get("/api/ncc-de-xuat/cong-no/{ncc_id}")
def cong_no_mot_ncc(
    ncc_id: str,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """1 NCC: tổng công nợ + các đơn mua còn nợ (FIFO — xem ghi chú đầu khối)."""
    from decimal import Decimal
    from muahang.app.models import PurchaseOrder, Supplier  # lazy
    sup = db.get(Supplier, ncc_id)
    if not sup:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy nhà cung cấp")
    by, no_rows = _tong_ncc(db, ncc_id)
    zero = Decimal("0")
    v = by.get(ncc_id) or {k: zero for k in _SO}
    don: dict[str, dict] = {}
    for e in no_rows:
        k = e.ref_order_id or ""
        d = don.setdefault(k, {"id": k, "ngay": e.ngay, "no_phai_tra": zero})
        d["no_phai_tra"] += e.so_tien or zero
        if e.ngay and (d["ngay"] is None or e.ngay < d["ngay"]):
            d["ngay"] = e.ngay
    ds = sorted(don.values(), key=lambda d: (d["ngay"] is None, d["ngay"] or ""))
    tra, dang = v["da_tra"], v["dang_de_xuat"]
    for d in ds:  # FIFO: trừ đã trả rồi đang đề xuất vào đơn cũ nhất trước
        t = min(tra, d["no_phai_tra"])
        tra -= t
        d["con_no"] = d["no_phai_tra"] - t
        g = min(dang, d["con_no"])
        dang -= g
        d["dang_de_xuat"] = g
        d["co_the_de_xuat"] = d["con_no"] - g
    ids = [d["id"] for d in ds if d["id"]]
    ten = {}
    if ids:
        ten = dict(db.execute(select(PurchaseOrder.id, PurchaseOrder.ten_don).where(PurchaseOrder.id.in_(ids))).all())
    return {
        "ncc": {"id": sup.id, "ten": sup.name, "ma": sup.short_code or sup.id},
        "tong": {k: float(v[k]) for k in _SO},
        "don": [{"id": d["id"], "ma": d["id"] or "(Không gắn đơn)", "ten_don": ten.get(d["id"]),
                 "ngay": d["ngay"].isoformat() if d["ngay"] else None,
                 **{k: float(d[k]) for k in ("no_phai_tra", "con_no", "dang_de_xuat", "co_the_de_xuat")}}
                for d in ds if d["con_no"] > 0],
    }


class DeXuatDong(BaseModel):
    ref_order_id: Optional[str] = None
    so_tien: float = Field(..., gt=0)


class DeXuatTaoBody(BaseModel):
    ncc_id: str = Field(..., min_length=1)
    ngay: Optional[str] = None
    mo_ta: Optional[str] = None
    dong: list[DeXuatDong] = Field(..., min_length=1)


@router.post("/api/ncc-de-xuat", status_code=status.HTTP_201_CREATED)
def tao_de_xuat_ncc(
    body: DeXuatTaoBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """Tạo 1 đề xuất trả NCC (muahang.congno loai='de_xuat_tra', trang_thai='cho_duyet') — đúng khuôn
    muahang POST /api/congno/de-xuat. Chọn 1 đơn → gắn ref_order_id; nhiều đơn → không gắn (như cách Mua
    Hàng đang làm), liệt kê đơn + số tiền vào mo_ta. Chặn tổng vượt số còn đề xuất được của NCC."""
    from datetime import date as _date
    from decimal import Decimal
    from muahang.app.models import CongNo, Supplier  # lazy
    from muahang.app.services import next_congno_id
    sup = db.get(Supplier, body.ncc_id)
    if not sup:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy nhà cung cấp")
    try:
        ngay = _date.fromisoformat(body.ngay) if body.ngay else _date.today()
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ngày không hợp lệ")
    tong = sum(Decimal(str(round(d.so_tien))) for d in body.dong)
    by, _ = _tong_ncc(db, body.ncc_id)
    toi_da = by[body.ncc_id]["co_the_de_xuat"] if body.ncc_id in by else Decimal("0")
    if tong > toi_da:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Tổng đề xuất {int(tong):,}đ vượt số còn đề xuất được của {sup.name}: {int(toi_da):,}đ")
    ds_don = "; ".join(f"{d.ref_order_id or 'Không gắn đơn'}: {int(round(d.so_tien)):,}đ" for d in body.dong)
    phan = [(body.mo_ta or "").strip(), f"Đơn: {ds_don}" if len(body.dong) > 1 else ""]
    mo_ta = "\n".join(x for x in phan if x) or None
    cid = next_congno_id(db)
    e = CongNo(
        id=cid, ncc_id=sup.id, ncc_name=sup.name, loai="de_xuat_tra",
        nguyen_gia=Decimal("0"), so_tien_giam=Decimal("0"), so_tien=tong,
        thang=ngay.strftime("%Y-%m"), ngay=ngay,
        ref_order_id=body.dong[0].ref_order_id if len(body.dong) == 1 else None,
        nv_mua_hang=user.username, mo_ta=mo_ta, nguoi_tao=user.username, trang_thai="cho_duyet",
    )
    e.lich_su = [{"action": "gui", "by": user.username,
                  "time": datetime.now(tz=timezone.utc).isoformat(), "note": None}]
    db.add(e)
    db.commit()
    log_action(db, app="ketoan", action="tao_de_xuat_ncc", user=user, request=request,
               resource=f"congno:{cid}", payload={"ncc_id": sup.id, "so_tien": str(tong)})
    return {"id": cid, "ncc": sup.name, "so_tien": float(tong)}


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


class ChiNCCBody(BaseModel):
    tai_khoan: str
    ghi_chu: Optional[str] = None
    # Ngày ghi sổ khoản chi. Bỏ trống = hôm nay (hành vi cũ).
    ngay_chi: Optional[_date] = None


def _ghi_giam_cong_no_ketoan(db: Session, e, *, by: str) -> Optional[str]:
    """Khoản vừa CHI làm GIẢM công nợ NCC bên Kế toán.

    GỘP 02/10/2026: phần việc chuyển hết sang
    `ketoan/app/services/giam_cong_no_ncc.py` để DÙNG CHUNG với cửa chi thứ hai
    (`de_nghi_tt.py::chi_denghitt`). Trước đó chỉ cửa này được vá, nên trả tiền
    bằng trang "Đề nghị Thanh Toán" vẫn không giảm công nợ Kế toán — và vì nó đặt
    `muahang.congno.da_chi=TRUE` nên sau đó cửa này trả 409, không bù lại được
    bằng giao diện (ca thật: phiếu quỹ #859, CHIẾN PHƯƠNG 70.000.000đ, phải vá tay).

    Hai cửa dùng CHUNG khoá `ref_id='mh-dexuat-{đề xuất Mua hàng}'` nên không thể
    ghi trùng nhau. KHÔNG commit — nằm chung transaction với phiếu sổ quỹ.
    """
    from ..services.giam_cong_no_ncc import ghi_giam_cong_no_ncc

    return ghi_giam_cong_no_ncc(
        db,
        ma_de_xuat_mh=e.id,
        ncc_ten=(e.ncc_name or e.ncc_id or ''),
        so_tien=e.so_tien,
        by=by,
        nguon='nút Chi trang Duyệt ĐX Trả NCC',
    )


@router.post("/api/ncc-de-xuat/{cid}/chi")
def chi_ncc(
    cid: str,
    body: ChiNCCBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """KT CHI đề xuất trả NCC đã DUYỆT XONG (trang_thai='duyet') → tạo sổ quỹ chi
    (trừ tài khoản) + đánh dấu da_chi → CÔNG NỢ NCC giảm (anh Quang 2026-08-20).
    Công nợ CHỈ giảm khi bấm Chi, không phải lúc duyệt. Idempotent (không chi 2 lần)."""
    if user.role not in _KT_ROLES and user.role not in _CEO_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ Kế Toán/CEO được chi")
    e = _get_or_404(db, cid)
    if (e.loai or "") != "de_xuat_tra":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không phải đề xuất trả NCC")
    if (e.trang_thai or "") != "duyet":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Đề xuất đang '{e.trang_thai}' — chỉ chi khi ĐÃ DUYỆT XONG (CEO duyệt)",
        )
    if getattr(e, "da_chi", False):
        raise HTTPException(status.HTTP_409_CONFLICT, "Đề xuất này đã chi rồi")
    tk = (body.tai_khoan or "").strip()
    if not tk:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Vui lòng chọn tài khoản chi")

    from datetime import date as _date_cls
    from decimal import Decimal
    try:
        from ..services.so_quy_auto import _upsert_so_quy, assert_du_chi
    except Exception as ex:  # pragma: no cover
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Không nạp được sổ quỹ: {ex}")
    # CHẶN chi làm số dư TK âm (anh Quang 2026-08-27)
    assert_du_chi(db, tk, e.so_tien)

    _gc = (body.ghi_chu or "").strip()
    # Đánh dấu đã chi + tạo sổ quỹ chi TRONG CÙNG transaction (commit hết hoặc rollback hết).
    e.da_chi = True
    e.tai_khoan_chi = tk
    e.ngay_chi = datetime.now(tz=timezone.utc)
    try:
        _upsert_so_quy(
            db,
            lien_quan="cong_no",
            ref_id=f"mh-dexuat-{e.id}",   # KHỚP ref bridge muahang approve_congno →
            ngay=_ngay_ghi_so(body.ngay_chi, _date_cls.today()),
            loai="chi",
            so_tien=Decimal(str(e.so_tien or 0)),
            tai_khoan=tk,
            noi_dung=f"Chi trả NCC {e.ncc_name or e.ncc_id or ''} — đề xuất {e.id}".strip(),
            mo_ta=((e.mo_ta or "") + (f" • {_gc}" if _gc else "")).strip() or None,
            phan_loai_cf="tra_ncc",
        )
        _ghi_giam_cong_no_ketoan(db, e, by=user.username)
        db.commit()
    except Exception as ex:
        db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Chi thất bại — sổ quỹ lỗi: {ex}")
    db.refresh(e)
    # Khoá Đề Nghị TT liên kết (nếu có) — đã chi ở trang NCC → TT không chi lại được.
    _dntt = getattr(e, "dntt_id", None)
    if _dntt:
        try:
            from sqlalchemy import text as _sqltext
            db.execute(
                _sqltext("UPDATE saleadmin.denghitt SET da_chi_ngoai = TRUE WHERE id = :d"),
                {"d": _dntt},
            )
            db.commit()
        except Exception:
            db.rollback()
    log_action(
        db, app="ketoan", action="chi_congno_dexuat", user=user, request=request,
        resource=f"congno:{cid}", payload={"tai_khoan": tk, "so_tien": str(e.so_tien)},
    )
    _safe_notify(
        db, target=(e.nguoi_tao or e.nv_mua_hang), by=user.username,
        source_app="muahang", event_type="congno:da_chi",
        title=f"[Trả NCC] Đã chi — {e.ncc_name or e.ncc_id or ''}",
        message=f"{int(e.so_tien or 0):,}đ qua {tk} • công nợ đã giảm",
        ref_type="congno", ref_id=e.id, url=f"{_MUAHANG_HOST}/", severity="success",
    )
    db.commit()
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
    # Có Đề nghị TT bản sao bên Sale Admin thì từ chối luôn, cùng giao dịch (ban_sao_de_nghi.py).
    kem = tu_choi_dntt_kem(db, dntt_id=getattr(e, "dntt_id", None), ly_do=body.ly_do, username=user.username)
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
        resource=f"congno:{cid}", payload={"ly_do": body.ly_do, "tu_choi_kem": kem},
    )
    return {**_to_dict(e, _build_name_map(db, [e])), "tu_choi_kem": kem}


@router.post("/api/ncc-de-xuat/{cid}/tu-choi-truoc-chi")
def tu_choi_truoc_chi(
    cid: str,
    body: TuChoiTruocChiBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """Từ chối đề xuất ĐÃ DUYỆT XONG (trang_thai='duyet', CEO đã duyệt ở Mua Hàng)
    NHƯNG CHƯA CHI — giám đốc yêu cầu 30/09/2026 (màn Duyệt chi tab "Chờ chi" thiếu
    nút Từ chối). Trước đây chỉ từ chối được ở cấp 1 (cho_duyet → kt_tu_choi, xem
    kt_reject phía trên) — đơn đã qua CEO duyệt là đường cụt, chỉ còn nút Chi.

    duyet → tu_choi (CÙNG trạng thái cuối với luồng "CEO từ chối" cũ, không phải
    trạng thái mới) — để "Sửa & gửi lại" bên Mua Hàng (congno.py:952
    gui_lai_congno_de_xuat, CHỈ ĐỌC không sửa) nhận diện đúng qua điều kiện có sẵn
    `trang_thai in ('kt_tu_choi', 'tu_choi')`, không cần Mua Hàng đổi gì.

    Ghi vào nguoi_duyet/ngay_duyet/ghi_chu_duyet (KHÔNG phải kt_duyet_boi/kt_ghi_chu)
    vì Mua Hàng đọc lý do từ chối lần trước qua `ghi_chu_duyet` khi trang_thai=='tu_choi'
    (congno.py:1001) — đặt sai cột thì "Gửi lại" hiện lý do rỗng.

    action lịch sử dùng "ceo_tu_choi" — action THẬT trong danh sách đóng của Mua
    Hàng (congno.py CongNo.lich_su comment: gui|kt_duyet|kt_tu_choi|ceo_duyet|
    ceo_tu_choi|sua_gui_lai), KHÔNG tự đặt action mới làm giao diện Mua Hàng vỡ
    nhãn — đúng ý nghĩa trạng thái (đơn đã qua CEO duyệt rồi mới bị từ chối), bất
    kể ai bấm (field `by` đã ghi rõ người bấm thật).
    """
    if user.role not in _KT_ROLES and user.role not in _CEO_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ Kế Toán/CEO được từ chối")
    e = _get_or_404(db, cid)
    if (e.trang_thai or "") != "duyet":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Đề xuất đang '{e.trang_thai}' — chỉ từ chối khi ĐÃ DUYỆT XONG, chưa chi",
        )
    if getattr(e, "da_chi", False):
        raise HTTPException(status.HTTP_409_CONFLICT, "Đề xuất này đã chi rồi — không thể từ chối")

    now = datetime.now(tz=timezone.utc)
    e.lich_su = [*(e.lich_su or []), {
        "action": "ceo_tu_choi", "by": user.username, "time": now.isoformat(),
        "note": body.ly_do.strip() or None,
    }]
    e.trang_thai = "tu_choi"
    e.nguoi_duyet = user.username
    e.ngay_duyet = now
    e.ghi_chu_duyet = body.ly_do
    # Từ chối luôn Đề nghị TT bản sao (nếu có) — không thì dòng bản sao vẫn chi được (ban_sao_de_nghi.py).
    kem = tu_choi_dntt_kem(db, dntt_id=getattr(e, "dntt_id", None), ly_do=body.ly_do, username=user.username)
    db.commit()
    db.refresh(e)
    _safe_notify(
        db, target=(e.nguoi_tao or e.nv_mua_hang), by=user.username,
        source_app="muahang", event_type="congno:rejected",
        title=f"[Đề xuất trả NCC] Từ chối trước khi chi — {e.ncc_name or e.ncc_id}",
        message=body.ly_do, ref_type="congno", ref_id=e.id, severity="warning",
    )
    db.commit()
    log_action(
        db, app="ketoan", action="tu_choi_truoc_chi_congno_dexuat", user=user, request=request,
        resource=f"congno:{cid}", payload={"ly_do": body.ly_do, "tu_choi_kem": kem},
    )
    return {**_to_dict(e, _build_name_map(db, [e])), "tu_choi_kem": kem}
