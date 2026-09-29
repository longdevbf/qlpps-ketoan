"""Quản Lý Vốn Vay — CRUD + workflow trả nợ + tự link sang so_quy/chi_phi.

Endpoints:
    GET    /api/khoan-vay                    — list (filter status, nguon)
    POST   /api/khoan-vay                    — tạo + auto giải ngân (so_quy thu)
    GET    /api/khoan-vay/{id}               — detail (lãi suất + giao dịch)
    PUT    /api/khoan-vay/{id}               — update info cơ bản
    DELETE /api/khoan-vay/{id}               — xoá (CASCADE giao dịch + lãi suất)
    POST   /api/khoan-vay/{id}/lai-suat      — đổi lãi suất từ ngày X
    POST   /api/khoan-vay/{id}/tra-goc       — trả gốc (so_quy chi)
    POST   /api/khoan-vay/{id}/tra-lai       — trả lãi (so_quy chi + chi_phi 'Lãi vay')
    POST   /api/khoan-vay/{id}/tra-goc-lai   — trả gốc+lãi 1 lần
    POST   /api/khoan-vay/{id}/tat-toan      — đánh dấu tất toán
    GET    /api/khoan-vay/{id}/lich-tra      — schedule dự kiến (theo phương thức)
    GET    /api/khoan-vay/summary            — tổng dư nợ + lãi YTD cho dashboard
"""
from datetime import date as date_cls, timedelta
from decimal import Decimal
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import (
    ChiPhiPhatSinh, KhoanVay, KhoanVayGiaoDich, KhoanVayLaiSuat,
    LoaiChiPhi, SoQuy, TaiKhoanNH, TaiKhoanNHGiaoDich,
)
from ..schemas import (
    KhoanVayCreate, KhoanVayDetailOut, KhoanVayOut, KhoanVayUpdate,
    LaiSuatCreate, TraGocBody, TraGocLaiBody, TraLaiBody,
)
from ..services.journal import post_journal
from ..services.tai_khoan_tien import tk_tien_cua
from ..services.tim_kiem import khop_khong_dau
from ._deps import require_ketoan_user


def _khoan_vay_account(ky_han_thang: Optional[int]) -> str:
    """≤ 12 tháng → 311 (vay ngắn hạn); > 12 → 341 (vay dài hạn)."""
    return "311" if (ky_han_thang or 0) <= 12 else "341"


def _cash_account(tk: Optional[TaiKhoanNH]) -> str:
    return tk_tien_cua(tk)


router = APIRouter()
_AUTH = Depends(require_ketoan_user)
_LOAI_LAI_VAY = "Lãi vay"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _serialize(kv: KhoanVay, db: Session, *, with_detail: bool = False) -> dict:
    """Build OUT dict + computed fields (da_tra_goc, con_lai_goc, da_tra_lai, lai_suat hiện tại)."""
    sums = db.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (KhoanVayGiaoDich.loai == "tra_goc", KhoanVayGiaoDich.so_tien),
                        (KhoanVayGiaoDich.loai == "tra_goc_lai", func.coalesce(KhoanVayGiaoDich.so_tien_goc, 0)),
                        else_=0,
                    )
                ), 0,
            ).label("tra_goc"),
            func.coalesce(
                func.sum(
                    case(
                        (KhoanVayGiaoDich.loai == "tra_lai", KhoanVayGiaoDich.so_tien),
                        (KhoanVayGiaoDich.loai == "tra_goc_lai", func.coalesce(KhoanVayGiaoDich.so_tien_lai, 0)),
                        else_=0,
                    )
                ), 0,
            ).label("tra_lai"),
        ).where(KhoanVayGiaoDich.khoan_vay_id == kv.id)
    ).one()
    da_tra_goc = Decimal(str(sums.tra_goc or 0))
    da_tra_lai = Decimal(str(sums.tra_lai or 0))
    con_lai_goc = max(Decimal("0"), kv.so_tien_vay - da_tra_goc)

    # Lãi suất hiện tại = MAX(tu_ngay) WHERE tu_ngay <= today
    today = date_cls.today()
    ls = db.execute(
        select(KhoanVayLaiSuat.lai_suat_nam)
        .where(KhoanVayLaiSuat.khoan_vay_id == kv.id)
        .where(KhoanVayLaiSuat.tu_ngay <= today)
        .order_by(KhoanVayLaiSuat.tu_ngay.desc())
        .limit(1)
    ).scalar()

    base = {
        "id": kv.id, "ma_khoan": kv.ma_khoan, "nguon_vay": kv.nguon_vay,
        "loai_vay": kv.loai_vay, "so_tien_vay": kv.so_tien_vay,
        "ngay_vay": kv.ngay_vay, "ky_han_thang": kv.ky_han_thang,
        "ngay_dao_han": kv.ngay_dao_han, "phuong_thuc_tra": kv.phuong_thuc_tra,
        "tai_san_the_chap": kv.tai_san_the_chap,
        "tai_khoan_giai_ngan": kv.tai_khoan_giai_ngan,
        "status": kv.status, "ghi_chu": kv.ghi_chu,
        "created_by": kv.created_by, "created_at": kv.created_at,
        "updated_at": kv.updated_at,
        "da_tra_goc": da_tra_goc, "con_lai_goc": con_lai_goc,
        "da_tra_lai": da_tra_lai,
        "lai_suat_hien_tai": ls,
    }
    if with_detail:
        base["lai_suats"] = [
            {
                "id": x.id, "tu_ngay": x.tu_ngay,
                "lai_suat_nam": x.lai_suat_nam, "ghi_chu": x.ghi_chu,
                "created_at": x.created_at,
            }
            for x in sorted(kv.lai_suats, key=lambda y: y.tu_ngay)
        ]
        base["giao_dichs"] = [
            {
                "id": g.id, "loai": g.loai, "ngay": g.ngay,
                "so_tien": g.so_tien, "so_tien_goc": g.so_tien_goc,
                "so_tien_lai": g.so_tien_lai,
                "ref_so_quy_id": g.ref_so_quy_id,
                "ref_chi_phi_id": g.ref_chi_phi_id,
                "ghi_chu": g.ghi_chu, "created_by": g.created_by,
                "created_at": g.created_at,
            }
            for g in sorted(kv.giao_dichs, key=lambda y: y.ngay)
        ]
    return base


def _add_months(d: date_cls, months: int) -> date_cls:
    """Cộng N tháng (đơn giản — clamp ngày cuối tháng nếu cần)."""
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    # clamp day
    import calendar
    last_day = calendar.monthrange(y, m)[1]
    return date_cls(y, m, min(d.day, last_day))


def _get_loai_lai_vay_id(db: Session) -> Optional[int]:
    """ID của loại chi phí 'Lãi vay' để link khi trả lãi."""
    return db.execute(
        select(LoaiChiPhi.id).where(LoaiChiPhi.ten == _LOAI_LAI_VAY)
    ).scalar()


# ─── Endpoints — list / detail / CRUD ─────────────────────────────────────────

@router.get("", response_model=list[dict])
def list_khoan_vay(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    status_filter: Optional[str] = Query(None, alias="status"),
    nguon_vay: Optional[str] = None,
):
    stmt = select(KhoanVay).order_by(KhoanVay.status, KhoanVay.ngay_vay.desc())
    if status_filter:
        stmt = stmt.where(KhoanVay.status == status_filter)
    if nguon_vay and nguon_vay.strip():
        # Lọc gõ tay theo tên bên cho vay — không phân biệt dấu + hoa/thường (services/tim_kiem.py).
        stmt = stmt.where(khop_khong_dau(KhoanVay.nguon_vay, nguon_vay))
    items = db.execute(stmt).scalars().all()
    return [_serialize(kv, db) for kv in items]


@router.get("/summary")
def summary(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Tổng dư nợ gốc + lãi đã trả YTD + sắp tới hạn cho dashboard."""
    items = db.execute(
        select(KhoanVay).where(KhoanVay.status == "dang_vay")
    ).scalars().all()

    tong_du_no_goc = Decimal("0")
    tong_lai_ytd = Decimal("0")
    today = date_cls.today()
    year_start = date_cls(today.year, 1, 1)

    for kv in items:
        s = _serialize(kv, db)
        tong_du_no_goc += s["con_lai_goc"]

    lai_ytd = db.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (KhoanVayGiaoDich.loai == "tra_lai", KhoanVayGiaoDich.so_tien),
                        (KhoanVayGiaoDich.loai == "tra_goc_lai", func.coalesce(KhoanVayGiaoDich.so_tien_lai, 0)),
                        else_=0,
                    )
                ), 0,
            )
        ).where(KhoanVayGiaoDich.ngay >= year_start, KhoanVayGiaoDich.ngay <= today)
    ).scalar() or Decimal("0")

    sap_dao_han = sum(
        1 for kv in items
        if kv.ngay_dao_han and 0 <= (kv.ngay_dao_han - today).days <= 30
    )

    return {
        "tong_du_no_goc": float(tong_du_no_goc),
        "tong_lai_ytd": float(lai_ytd),
        "n_khoan_dang_vay": len(items),
        "n_khoan_sap_dao_han_30d": sap_dao_han,
    }


@router.get("/{kv_id}", response_model=KhoanVayDetailOut)
def get_khoan_vay(
    kv_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    kv = db.execute(
        select(KhoanVay)
        .options(selectinload(KhoanVay.lai_suats), selectinload(KhoanVay.giao_dichs))
        .where(KhoanVay.id == kv_id)
    ).scalar_one_or_none()
    if not kv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Khoản vay không tồn tại")
    return _serialize(kv, db, with_detail=True)


@router.post("", response_model=KhoanVayDetailOut, status_code=status.HTTP_201_CREATED)
def create_khoan_vay(
    body: KhoanVayCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    if user.role not in ("admin", "ceo", "assistant_ceo", "manager", "kt"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền tạo khoản vay")

    # Validate tai_khoan_giai_ngan: nếu có thì phải khớp ten_tk trong tai_khoan_nh
    # (tránh bug FE submit "[object Object]" khiến so_quy không match → âm quỹ)
    if body.tai_khoan_giai_ngan:
        exists = db.execute(
            select(TaiKhoanNH.id)
            .where(TaiKhoanNH.ten_tk == body.tai_khoan_giai_ngan)
            .where(TaiKhoanNH.active.is_(True))
        ).scalar()
        if not exists:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Tài khoản giải ngân {body.tai_khoan_giai_ngan!r} không tồn tại "
                f"hoặc đã ngưng hoạt động. Vui lòng chọn từ danh sách Tài Khoản NH.",
            )

    # Auto-compute ngay_dao_han
    ngay_dao_han = _add_months(body.ngay_vay, body.ky_han_thang)

    kv = KhoanVay(
        ma_khoan=body.ma_khoan,
        nguon_vay=body.nguon_vay,
        loai_vay=body.loai_vay,
        so_tien_vay=body.so_tien_vay,
        ngay_vay=body.ngay_vay,
        ky_han_thang=body.ky_han_thang,
        ngay_dao_han=ngay_dao_han,
        phuong_thuc_tra=body.phuong_thuc_tra,
        tai_san_the_chap=body.tai_san_the_chap,
        tai_khoan_giai_ngan=body.tai_khoan_giai_ngan,
        status="dang_vay",
        ghi_chu=body.ghi_chu,
        created_by=user.username,
    )
    db.add(kv)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mã khoản {body.ma_khoan!r} đã tồn tại")

    # Lãi suất ban đầu
    db.add(KhoanVayLaiSuat(
        khoan_vay_id=kv.id, tu_ngay=body.ngay_vay,
        lai_suat_nam=body.lai_suat_nam,
        ghi_chu="Lãi suất ban đầu", created_by=user.username,
    ))

    # Auto giải ngân: tạo so_quy thu + giao_dich
    if body.auto_giai_ngan:
        sq = SoQuy(
            ngay=body.ngay_vay, loai="thu", so_tien=body.so_tien_vay,
            tai_khoan=body.tai_khoan_giai_ngan,
            noi_dung=f"Giải ngân vay {body.ma_khoan}",
            lien_quan=f"vay_{kv.id}",
            ref_id=str(kv.id),
            phan_loai_cf="vay_nh",
            created_by=user.username,
        )
        db.add(sq)
        db.flush()
        db.add(KhoanVayGiaoDich(
            khoan_vay_id=kv.id, loai="giai_ngan", ngay=body.ngay_vay,
            so_tien=body.so_tien_vay, ref_so_quy_id=sq.id,
            ghi_chu="Giải ngân tự động khi tạo khoản vay",
            created_by=user.username,
        ))

    # Phase 2 — Double-entry posting khi có tai_khoan_id
    if body.tai_khoan_id:
        tk = db.get(TaiKhoanNH, body.tai_khoan_id)
        if not tk:
            db.rollback()
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"tai_khoan_id={body.tai_khoan_id} không tồn tại",
            )
        cash_acc = _cash_account(tk)
        loan_acc = _khoan_vay_account(body.ky_han_thang)
        gd = TaiKhoanNHGiaoDich(
            ngay=body.ngay_vay, tai_khoan_id=tk.id, loai="thu",
            so_tien=body.so_tien_vay,
            doi_tac=body.nguon_vay,
            ghi_chu=f"Giải ngân vay {body.ma_khoan} ({body.nguon_vay})",
            source_app="khoan_vay", source_doc_id=f"khoan_vay_{kv.id}",
            created_by=user.username,
        )
        db.add(gd)
        db.flush()
        post_journal(
            db, ngay=body.ngay_vay,
            mo_ta=f"Tạo khoản vay {body.ma_khoan} — nhận tiền vào {tk.ten_tk}",
            source_type="tao_khoan_vay", source_id=str(kv.id),
            by_user=user.username,
            lines=[
                {"loai": "no", "account_code": cash_acc,
                 "ref_table": "tai_khoan_nh", "ref_id": tk.id,
                 "so_tien": body.so_tien_vay,
                 "ghi_chu": f"Nhận tiền vay vào {tk.ten_tk}"},
                {"loai": "co", "account_code": loan_acc,
                 "ref_table": "khoan_vay", "ref_id": kv.id,
                 "so_tien": body.so_tien_vay,
                 "ghi_chu": f"Vay {body.nguon_vay}"},
            ],
        )

    db.commit()
    db.refresh(kv)
    log_action(
        db, app="ketoan", action="create_khoan_vay", user=user, request=request,
        resource=f"khoan_vay:{kv.id}",
        payload={"ma_khoan": kv.ma_khoan, "so_tien": float(kv.so_tien_vay)},
    )
    # Reload với eager load để serialize
    kv = db.execute(
        select(KhoanVay)
        .options(selectinload(KhoanVay.lai_suats), selectinload(KhoanVay.giao_dichs))
        .where(KhoanVay.id == kv.id)
    ).scalar_one()
    return _serialize(kv, db, with_detail=True)


@router.put("/{kv_id}", response_model=KhoanVayOut)
def update_khoan_vay(
    kv_id: int, body: KhoanVayUpdate, request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    if user.role not in ("admin", "ceo", "assistant_ceo", "manager", "kt"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền")
    kv = db.get(KhoanVay, kv_id)
    if not kv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Khoản vay không tồn tại")

    fields = body.model_dump(exclude_unset=True)
    # tai_khoan_id không phải column model — tách ra để xử lý backfill/propagate riêng
    new_tk_id = fields.pop("tai_khoan_id", None)

    # Validate tai_khoan_giai_ngan (nếu update) — chống lưu rác như '[object Object]'
    new_ten_tk = fields.get("tai_khoan_giai_ngan")
    tk_changed = "tai_khoan_giai_ngan" in fields
    old_ten_tk = kv.tai_khoan_giai_ngan
    if new_ten_tk:
        ok = db.execute(
            select(TaiKhoanNH.id)
            .where(TaiKhoanNH.ten_tk == new_ten_tk)
            .where(TaiKhoanNH.active.is_(True))
        ).scalar()
        if not ok:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Tài khoản {new_ten_tk!r} không tồn tại hoặc đã ngưng.",
            )

    for k, v in fields.items():
        setattr(kv, k, v)
    if "ngay_vay" in fields or "ky_han_thang" in fields:
        kv.ngay_dao_han = _add_months(kv.ngay_vay, kv.ky_han_thang)
    db.commit()
    db.refresh(kv)

    # ─── Propagate đổi TK Giải ngân sang Sổ Quỹ + Tài Khoản NH giao dịch ─────
    # Khi user đổi TK Giải ngân ở form sửa vốn vay, các record cross-table phải
    # cập nhật theo (giải ngân ban đầu): so_quy (loai='thu', lien_quan=vay_X)
    # và tai_khoan_nh_giao_dich (source_doc_id=khoan_vay_X). Nếu chưa có M4
    # (khoản vay cũ) → backfill như trước. tránh "đổi TK xong mà sổ quỹ + TK NH
    # vẫn ghi tên cũ" làm số dư + báo cáo lệch.
    new_tk: Optional[TaiKhoanNH] = None
    if new_tk_id:
        new_tk = db.get(TaiKhoanNH, new_tk_id)
        if not new_tk:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"tai_khoan_id={new_tk_id} không tồn tại",
            )
    elif tk_changed and new_ten_tk:
        # FE chỉ gửi tên TK → resolve sang TaiKhoanNH để có id propagate sang M4
        new_tk = db.execute(
            select(TaiKhoanNH)
            .where(TaiKhoanNH.ten_tk == new_ten_tk)
            .where(TaiKhoanNH.active.is_(True))
        ).scalar_one_or_none()

    if new_tk or (tk_changed and new_ten_tk != old_ten_tk):
        from sqlalchemy import text as _text
        ten_for_so_quy = (new_tk.ten_tk if new_tk else new_ten_tk)

        # 1) Sổ Quỹ — cập nhật MỌI giao dịch của khoản vay này (cả giải ngân
        # 'thu' và trả gốc/lãi 'chi' đang trỏ tới TK cũ) sang TK mới. Trả gốc/
        # lãi không truyền tai_khoan riêng đều default về kv.tai_khoan_giai_ngan
        # (xem _create_so_quy_chi) → khi đổi TK Giải ngân ở master, các dòng
        # đó cũng phải theo. Chỉ giữ nguyên dòng nào tai_khoan đã # khác cả 2
        # giá trị (user đã chủ động chọn TK lệch — không đụng).
        db.execute(
            _text("""
                UPDATE ketoan.so_quy
                SET tai_khoan = :new_ten
                WHERE lien_quan = :lq
                  AND (tai_khoan = :old_ten OR tai_khoan IS NULL)
            """),
            {"new_ten": ten_for_so_quy, "old_ten": old_ten_tk or "",
             "lq": f"vay_{kv.id}"},
        )

        # 2) Tài Khoản NH giao dịch — đổi tai_khoan_id của tất cả giao dịch
        # liên quan khoản vay này (giải ngân + trả nợ) sang TK mới khi:
        #   • giao dịch hiện đang trỏ TK cũ (so khớp tai_khoan_id), HOẶC
        #   • là giao dịch giải ngân initial (source_doc_id=khoan_vay_X)
        # Journal lines (kế toán nội bộ) giữ nguyên — bản ghi audit gốc.
        if new_tk:
            old_tk_id = None
            if old_ten_tk:
                old_tk_id = db.execute(
                    select(TaiKhoanNH.id).where(TaiKhoanNH.ten_tk == old_ten_tk)
                ).scalar()

            # 2a) giải ngân initial
            existing_m4 = db.execute(
                select(TaiKhoanNHGiaoDich)
                .where(TaiKhoanNHGiaoDich.source_app == "khoan_vay")
                .where(TaiKhoanNHGiaoDich.source_doc_id == f"khoan_vay_{kv.id}")
                .where(TaiKhoanNHGiaoDich.loai == "thu")
            ).scalar_one_or_none()

            if existing_m4:
                existing_m4.tai_khoan_id = new_tk.id
                existing_m4.ghi_chu = (
                    f"Giải ngân vay {kv.ma_khoan} ({kv.nguon_vay}) "
                    f"— TK Giải ngân: {new_tk.ten_tk}"
                )
            else:
                # Backfill khoản vay cũ chưa có M4
                cash_acc = _cash_account(new_tk)
                loan_acc = _khoan_vay_account(kv.ky_han_thang)
                gd = TaiKhoanNHGiaoDich(
                    ngay=kv.ngay_vay, tai_khoan_id=new_tk.id, loai="thu",
                    so_tien=kv.so_tien_vay, doi_tac=kv.nguon_vay,
                    ghi_chu=f"Giải ngân vay {kv.ma_khoan} (backfill khi sửa)",
                    source_app="khoan_vay", source_doc_id=f"khoan_vay_{kv.id}",
                    created_by=user.username,
                )
                db.add(gd)
                db.flush()
                post_journal(
                    db, ngay=kv.ngay_vay,
                    mo_ta=f"Backfill giải ngân vay {kv.ma_khoan} vào {new_tk.ten_tk}",
                    source_type="tao_khoan_vay", source_id=str(kv.id),
                    by_user=user.username,
                    lines=[
                        {"loai": "no", "account_code": cash_acc,
                         "ref_table": "tai_khoan_nh", "ref_id": new_tk.id,
                         "so_tien": kv.so_tien_vay,
                         "ghi_chu": f"Nhận tiền vay vào {new_tk.ten_tk}"},
                        {"loai": "co", "account_code": loan_acc,
                         "ref_table": "khoan_vay", "ref_id": kv.id,
                         "so_tien": kv.so_tien_vay,
                         "ghi_chu": f"Vay {kv.nguon_vay}"},
                    ],
                )

            # 2b) Tất cả giao dịch trả gốc/lãi (source_doc_id=khoan_vay_gd_*)
            # đang trỏ TK cũ → đổi sang TK mới
            if old_tk_id and old_tk_id != new_tk.id:
                db.execute(
                    _text("""
                        UPDATE ketoan.tai_khoan_nh_giao_dich
                        SET tai_khoan_id = :new_id
                        WHERE source_app = 'khoan_vay'
                          AND source_doc_id LIKE :prefix
                          AND tai_khoan_id = :old_id
                          AND loai = 'chi'
                    """),
                    {"new_id": new_tk.id, "old_id": old_tk_id,
                     "prefix": "khoan_vay_gd_%"},
                )

        db.commit()

    log_action(
        db, app="ketoan", action="update_khoan_vay", user=user, request=request,
        resource=f"khoan_vay:{kv_id}", payload=fields,
    )
    return _serialize(kv, db)


@router.delete("/{kv_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_khoan_vay(
    kv_id: int, request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    if user.role not in ("admin", "ceo"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ admin/ceo được xoá khoản vay")
    kv = db.get(KhoanVay, kv_id)
    if not kv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Khoản vay không tồn tại")
    ma = kv.ma_khoan
    db.delete(kv)
    db.commit()
    log_action(
        db, app="ketoan", action="delete_khoan_vay", user=user, request=request,
        resource=f"khoan_vay:{kv_id}", payload={"ma_khoan": ma},
    )


# ─── Đổi lãi suất ─────────────────────────────────────────────────────────────

@router.post("/{kv_id}/lai-suat", status_code=status.HTTP_201_CREATED)
def doi_lai_suat(
    kv_id: int, body: LaiSuatCreate, request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    kv = db.get(KhoanVay, kv_id)
    if not kv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Khoản vay không tồn tại")
    ls = KhoanVayLaiSuat(
        khoan_vay_id=kv_id, tu_ngay=body.tu_ngay,
        lai_suat_nam=body.lai_suat_nam, ghi_chu=body.ghi_chu,
        created_by=user.username,
    )
    db.add(ls)
    db.commit()
    db.refresh(ls)
    log_action(
        db, app="ketoan", action="doi_lai_suat_khoan_vay", user=user, request=request,
        resource=f"khoan_vay:{kv_id}",
        payload={"tu_ngay": str(body.tu_ngay), "lai_suat_nam": float(body.lai_suat_nam)},
    )
    return {
        "ok": True, "id": ls.id, "tu_ngay": ls.tu_ngay,
        "lai_suat_nam": float(ls.lai_suat_nam),
    }


# ─── Trả gốc / lãi / gốc+lãi ──────────────────────────────────────────────────

def _create_so_quy_chi(
    db: Session, kv: KhoanVay, ngay: date_cls, so_tien: Decimal,
    tai_khoan: Optional[str], noi_dung: str, user: JWTPayload,
) -> SoQuy:
    sq = SoQuy(
        ngay=ngay, loai="chi", so_tien=so_tien,
        tai_khoan=tai_khoan or kv.tai_khoan_giai_ngan,
        noi_dung=noi_dung, lien_quan=f"vay_{kv.id}",
        ref_id=str(kv.id),
        phan_loai_cf="tra_nh",
        created_by=user.username,
    )
    db.add(sq)
    db.flush()
    return sq


def _create_chi_phi_lai_vay(
    db: Session, kv: KhoanVay, ngay: date_cls, so_tien: Decimal,
    tai_khoan: Optional[str], ghi_chu: str, user: JWTPayload,
) -> ChiPhiPhatSinh:
    cp = ChiPhiPhatSinh(
        ngay=ngay, so_tien=so_tien,
        loai_chi_phi=_LOAI_LAI_VAY,
        ngan_hang=tai_khoan or kv.tai_khoan_giai_ngan,
        nguoi_chi=user.username,
        mo_ta=f"Trả lãi vay {kv.ma_khoan} ({kv.nguon_vay})",
        ghi_chu=ghi_chu,
        created_by=user.username,
    )
    db.add(cp)
    db.flush()
    return cp


@router.post("/{kv_id}/tra-goc", status_code=status.HTTP_201_CREATED)
def tra_goc(
    kv_id: int, body: TraGocBody, request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    kv = db.get(KhoanVay, kv_id)
    if not kv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Khoản vay không tồn tại")
    sq = _create_so_quy_chi(
        db, kv, body.ngay, body.so_tien, body.tai_khoan,
        f"Trả gốc vay {kv.ma_khoan}", user,
    )
    gd = KhoanVayGiaoDich(
        khoan_vay_id=kv_id, loai="tra_goc", ngay=body.ngay,
        so_tien=body.so_tien, ref_so_quy_id=sq.id,
        ghi_chu=body.ghi_chu, created_by=user.username,
    )
    db.add(gd)
    db.flush()

    # Phase 2 — double-entry: Nợ 311|341 / Có 112
    if body.tai_khoan_id:
        tk = db.get(TaiKhoanNH, body.tai_khoan_id)
        if not tk:
            db.rollback()
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"tai_khoan_id={body.tai_khoan_id} không tồn tại",
            )
        cash_acc = _cash_account(tk)
        loan_acc = _khoan_vay_account(kv.ky_han_thang)
        tknhgd = TaiKhoanNHGiaoDich(
            ngay=body.ngay, tai_khoan_id=tk.id, loai="chi",
            so_tien=body.so_tien, doi_tac=kv.nguon_vay,
            ghi_chu=f"Trả gốc vay {kv.ma_khoan}",
            source_app="khoan_vay", source_doc_id=f"khoan_vay_gd_{gd.id}",
            created_by=user.username,
        )
        db.add(tknhgd)
        db.flush()
        post_journal(
            db, ngay=body.ngay,
            mo_ta=f"Trả gốc vay {kv.ma_khoan} từ {tk.ten_tk}",
            source_type="tra_no_vay", source_id=str(gd.id),
            by_user=user.username,
            lines=[
                {"loai": "no", "account_code": loan_acc,
                 "ref_table": "khoan_vay", "ref_id": kv.id,
                 "so_tien": body.so_tien,
                 "ghi_chu": f"Giảm dư nợ gốc {kv.ma_khoan}"},
                {"loai": "co", "account_code": cash_acc,
                 "ref_table": "tai_khoan_nh", "ref_id": tk.id,
                 "so_tien": body.so_tien,
                 "ghi_chu": f"Chi từ {tk.ten_tk}"},
            ],
        )

    db.commit()
    log_action(
        db, app="ketoan", action="tra_goc_khoan_vay", user=user, request=request,
        resource=f"khoan_vay:{kv_id}",
        payload={"so_tien": float(body.so_tien), "ngay": str(body.ngay),
                 "tai_khoan_id": body.tai_khoan_id},
    )
    return {"ok": True, "giao_dich_id": gd.id, "so_quy_id": sq.id}


@router.post("/{kv_id}/tra-lai", status_code=status.HTTP_201_CREATED)
def tra_lai(
    kv_id: int, body: TraLaiBody, request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    kv = db.get(KhoanVay, kv_id)
    if not kv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Khoản vay không tồn tại")
    sq = _create_so_quy_chi(
        db, kv, body.ngay, body.so_tien, body.tai_khoan,
        f"Trả lãi vay {kv.ma_khoan}", user,
    )
    cp = _create_chi_phi_lai_vay(
        db, kv, body.ngay, body.so_tien, body.tai_khoan,
        body.ghi_chu or "", user,
    )
    gd = KhoanVayGiaoDich(
        khoan_vay_id=kv_id, loai="tra_lai", ngay=body.ngay,
        so_tien=body.so_tien, ref_so_quy_id=sq.id, ref_chi_phi_id=cp.id,
        ghi_chu=body.ghi_chu, created_by=user.username,
    )
    db.add(gd)
    db.flush()

    # Phase 2 — Nợ 635 (chi phí lãi vay) / Có 112
    if body.tai_khoan_id:
        tk = db.get(TaiKhoanNH, body.tai_khoan_id)
        if not tk:
            db.rollback()
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"tai_khoan_id={body.tai_khoan_id} không tồn tại",
            )
        cash_acc = _cash_account(tk)
        tknhgd = TaiKhoanNHGiaoDich(
            ngay=body.ngay, tai_khoan_id=tk.id, loai="chi",
            so_tien=body.so_tien, doi_tac=kv.nguon_vay,
            ghi_chu=f"Trả lãi vay {kv.ma_khoan}",
            source_app="khoan_vay", source_doc_id=f"khoan_vay_gd_{gd.id}",
            created_by=user.username,
        )
        db.add(tknhgd)
        db.flush()
        post_journal(
            db, ngay=body.ngay,
            mo_ta=f"Trả lãi vay {kv.ma_khoan} từ {tk.ten_tk}",
            source_type="tra_no_vay", source_id=str(gd.id),
            by_user=user.username,
            lines=[
                {"loai": "no", "account_code": "635",
                 "ref_table": "chi_phi_phat_sinh", "ref_id": cp.id,
                 "so_tien": body.so_tien,
                 "ghi_chu": f"Lãi vay {kv.ma_khoan}"},
                {"loai": "co", "account_code": cash_acc,
                 "ref_table": "tai_khoan_nh", "ref_id": tk.id,
                 "so_tien": body.so_tien,
                 "ghi_chu": f"Chi từ {tk.ten_tk}"},
            ],
        )

    db.commit()
    log_action(
        db, app="ketoan", action="tra_lai_khoan_vay", user=user, request=request,
        resource=f"khoan_vay:{kv_id}",
        payload={"so_tien": float(body.so_tien), "ngay": str(body.ngay),
                 "tai_khoan_id": body.tai_khoan_id},
    )
    return {
        "ok": True, "giao_dich_id": gd.id,
        "so_quy_id": sq.id, "chi_phi_id": cp.id,
    }


@router.post("/{kv_id}/tra-goc-lai", status_code=status.HTTP_201_CREATED)
def tra_goc_lai(
    kv_id: int, body: TraGocLaiBody, request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    kv = db.get(KhoanVay, kv_id)
    if not kv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Khoản vay không tồn tại")
    tong = body.so_tien_goc + body.so_tien_lai
    sq = _create_so_quy_chi(
        db, kv, body.ngay, tong, body.tai_khoan,
        f"Trả gốc+lãi vay {kv.ma_khoan} (gốc {body.so_tien_goc:,.0f} + lãi {body.so_tien_lai:,.0f})",
        user,
    )
    cp_id = None
    if body.so_tien_lai > 0:
        cp = _create_chi_phi_lai_vay(
            db, kv, body.ngay, body.so_tien_lai, body.tai_khoan,
            body.ghi_chu or "", user,
        )
        cp_id = cp.id
    gd = KhoanVayGiaoDich(
        khoan_vay_id=kv_id, loai="tra_goc_lai", ngay=body.ngay,
        so_tien=tong, so_tien_goc=body.so_tien_goc, so_tien_lai=body.so_tien_lai,
        ref_so_quy_id=sq.id, ref_chi_phi_id=cp_id,
        ghi_chu=body.ghi_chu, created_by=user.username,
    )
    db.add(gd)
    db.flush()

    # Phase 2 — Nợ (311|341 + 635) / Có 112 (1 bút toán nhiều dòng)
    if body.tai_khoan_id:
        tk = db.get(TaiKhoanNH, body.tai_khoan_id)
        if not tk:
            db.rollback()
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"tai_khoan_id={body.tai_khoan_id} không tồn tại",
            )
        cash_acc = _cash_account(tk)
        loan_acc = _khoan_vay_account(kv.ky_han_thang)
        tknhgd = TaiKhoanNHGiaoDich(
            ngay=body.ngay, tai_khoan_id=tk.id, loai="chi",
            so_tien=tong, doi_tac=kv.nguon_vay,
            ghi_chu=f"Trả gốc+lãi vay {kv.ma_khoan}",
            source_app="khoan_vay", source_doc_id=f"khoan_vay_gd_{gd.id}",
            created_by=user.username,
        )
        db.add(tknhgd)
        db.flush()
        lines: list[dict] = []
        if body.so_tien_goc and body.so_tien_goc > 0:
            lines.append({
                "loai": "no", "account_code": loan_acc,
                "ref_table": "khoan_vay", "ref_id": kv.id,
                "so_tien": body.so_tien_goc,
                "ghi_chu": f"Giảm dư nợ gốc {kv.ma_khoan}",
            })
        if body.so_tien_lai and body.so_tien_lai > 0:
            lines.append({
                "loai": "no", "account_code": "635",
                "ref_table": "chi_phi_phat_sinh", "ref_id": cp_id,
                "so_tien": body.so_tien_lai,
                "ghi_chu": f"Lãi vay {kv.ma_khoan}",
            })
        lines.append({
            "loai": "co", "account_code": cash_acc,
            "ref_table": "tai_khoan_nh", "ref_id": tk.id,
            "so_tien": tong,
            "ghi_chu": f"Chi từ {tk.ten_tk}",
        })
        post_journal(
            db, ngay=body.ngay,
            mo_ta=f"Trả gốc+lãi {kv.ma_khoan} từ {tk.ten_tk}",
            source_type="tra_no_vay", source_id=str(gd.id),
            by_user=user.username, lines=lines,
        )

    db.commit()
    log_action(
        db, app="ketoan", action="tra_goc_lai_khoan_vay", user=user, request=request,
        resource=f"khoan_vay:{kv_id}",
        payload={
            "ngay": str(body.ngay),
            "goc": float(body.so_tien_goc), "lai": float(body.so_tien_lai),
            "tai_khoan_id": body.tai_khoan_id,
        },
    )
    return {
        "ok": True, "giao_dich_id": gd.id,
        "so_quy_id": sq.id, "chi_phi_id": cp_id,
    }


@router.post("/{kv_id}/tat-toan")
def tat_toan(
    kv_id: int, request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    kv = db.get(KhoanVay, kv_id)
    if not kv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Khoản vay không tồn tại")
    kv.status = "da_tat_toan"
    db.commit()
    log_action(
        db, app="ketoan", action="tat_toan_khoan_vay", user=user, request=request,
        resource=f"khoan_vay:{kv_id}", payload={"ma_khoan": kv.ma_khoan},
    )
    return {"ok": True, "status": "da_tat_toan"}


# ─── Lịch trả dự kiến (helper read-only) ──────────────────────────────────────

@router.get("/{kv_id}/lich-tra")
def lich_tra(
    kv_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Sinh lịch trả dự kiến theo phương thức.

    - tra_deu: gốc+lãi đều mỗi tháng (annuity formula)
    - chi_lai_dinh_ky: trả lãi mỗi tháng + gốc cuối kỳ
    - goc_lai_cuoi_ky: cuối kỳ trả tất (gốc + lãi cộng dồn)
    - tu_do: trả [] (anh tự chủ động)
    """
    kv = db.execute(
        select(KhoanVay).options(selectinload(KhoanVay.lai_suats)).where(KhoanVay.id == kv_id)
    ).scalar_one_or_none()
    if not kv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Khoản vay không tồn tại")

    # Lấy lãi suất hiện tại để dự kiến
    today = date_cls.today()
    ls_now = next(
        (l.lai_suat_nam for l in sorted(kv.lai_suats, key=lambda x: x.tu_ngay, reverse=True)
         if l.tu_ngay <= today),
        Decimal("8.0"),
    )
    lai_thang = float(ls_now) / 12.0 / 100.0  # %

    items = []
    if kv.phuong_thuc_tra == "tu_do":
        return {"ok": True, "items": [], "note": "Phương thức tự do — không có lịch dự kiến"}

    if kv.phuong_thuc_tra == "goc_lai_cuoi_ky":
        n = kv.ky_han_thang
        tong_lai = float(kv.so_tien_vay) * lai_thang * n
        items.append({
            "ngay": (kv.ngay_dao_han or _add_months(kv.ngay_vay, n)).isoformat(),
            "loai": "tra_goc_lai",
            "so_tien_goc": float(kv.so_tien_vay),
            "so_tien_lai": round(tong_lai, 2),
            "so_tien_tong": float(kv.so_tien_vay) + round(tong_lai, 2),
        })
    elif kv.phuong_thuc_tra == "chi_lai_dinh_ky":
        for k in range(1, kv.ky_han_thang + 1):
            d = _add_months(kv.ngay_vay, k)
            lai = float(kv.so_tien_vay) * lai_thang
            items.append({
                "ngay": d.isoformat(), "loai": "tra_lai",
                "so_tien_goc": 0,
                "so_tien_lai": round(lai, 2),
                "so_tien_tong": round(lai, 2),
            })
        # Cuối kỳ trả gốc
        items.append({
            "ngay": (kv.ngay_dao_han or _add_months(kv.ngay_vay, kv.ky_han_thang)).isoformat(),
            "loai": "tra_goc",
            "so_tien_goc": float(kv.so_tien_vay),
            "so_tien_lai": 0,
            "so_tien_tong": float(kv.so_tien_vay),
        })
    elif kv.phuong_thuc_tra == "tra_deu":
        # Annuity formula: PMT = P * r * (1+r)^n / ((1+r)^n - 1)
        P = float(kv.so_tien_vay)
        r = lai_thang
        n = kv.ky_han_thang
        if r > 0:
            pmt = P * r * (1 + r) ** n / ((1 + r) ** n - 1)
        else:
            pmt = P / n
        con_lai = P
        for k in range(1, n + 1):
            lai = con_lai * r
            goc = pmt - lai
            items.append({
                "ngay": _add_months(kv.ngay_vay, k).isoformat(),
                "loai": "tra_goc_lai",
                "so_tien_goc": round(goc, 2),
                "so_tien_lai": round(lai, 2),
                "so_tien_tong": round(pmt, 2),
            })
            con_lai -= goc

    return {"ok": True, "phuong_thuc_tra": kv.phuong_thuc_tra, "items": items}
