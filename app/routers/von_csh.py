"""Vốn Chủ Sở Hữu (VCSH) + Quỹ DN — API.

Endpoints:
    # VCSH
    GET    /api/von-csh                       (list, filter from/to, loai)
    POST   /api/von-csh/gop-von               (body: ngay, so_tien, chu_so_huu, ghi_chu)
    POST   /api/von-csh/rut-von
    POST   /api/von-csh/chia-co-tuc
    POST   /api/von-csh/trich-quy             (body có thêm `quy_id`, update quy_dn.so_du)
    POST   /api/von-csh/khoi-tao-ban-dau      (1 lần — chặn nếu đã có gop_von trước đó)
    GET    /api/von-csh/summary               (tổng các loại + danh sách quỹ DN)
    DELETE /api/von-csh/{id}                  (admin only — undo trích quỹ phải hoàn lại)

    # Quỹ DN
    GET    /api/quy-dn
    POST   /api/quy-dn
    PUT    /api/quy-dn/{id}
"""
from datetime import date as date_cls
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import QuyDN, SoQuy, TaiKhoanNH, TaiKhoanNHGiaoDich, VonCSH
from ..schemas import (
    GopVonBody, KhoiTaoBanDauBody, QuyDNCreate, QuyDNOut, QuyDNUpdate,
    TrichQuyBody, VonCSHOut, VonCSHSummary,
)
from ..services.journal import map_quy_to_account, post_journal
from ..services.so_quy_auto import assert_du_chi as _assert_du_chi
from ..services.quy_dn_calc import nap_quy as _nap_quy_dn, void_giao_dich as _void_quy_gd
from ._deps import require_ketoan_user


router = APIRouter()
quy_router = APIRouter()
_AUTH = Depends(require_ketoan_user)


def _require_vcsh_admin(user) -> None:
    """Thao tác VỐN CHỦ SỞ HỮU (góp/rút/cổ tức/trích quỹ) là đường tiền lớn —
    chỉ CEO/admin (đồng bộ với khoi_tao_ban_dau + delete_von_csh)."""
    if user.role not in ("admin", "ceo"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Chỉ CEO/admin được thao tác vốn chủ sở hữu",
        )


_LOAI_VCSH = {"gop_von", "rut_von", "chia_co_tuc", "trich_quy", "dieu_chinh"}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _serialize(v: VonCSH) -> dict:
    return {
        "id": v.id, "ngay": v.ngay,
        "loai_giao_dich": v.loai_giao_dich,
        "so_tien": v.so_tien, "chu_so_huu": v.chu_so_huu,
        "quy_id": v.quy_id, "ghi_chu": v.ghi_chu,
        "source_doc_id": v.source_doc_id,
        "created_by": v.created_by, "created_at": v.created_at,
    }


def _ghi_giao_dich(
    db: Session, *, loai: str, ngay: date_cls, so_tien: Decimal,
    chu_so_huu: Optional[str], ghi_chu: Optional[str],
    source_doc_id: Optional[str] = None, quy_id: Optional[int] = None,
    user: JWTPayload,
) -> VonCSH:
    if loai not in _LOAI_VCSH:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"loai_giao_dich {loai!r} không hợp lệ",
        )
    obj = VonCSH(
        ngay=ngay, loai_giao_dich=loai, so_tien=so_tien,
        chu_so_huu=chu_so_huu, ghi_chu=ghi_chu,
        source_doc_id=source_doc_id, quy_id=quy_id,
        created_by=user.username,
    )
    db.add(obj)
    db.flush()
    return obj


def _ensure_tk_nh(db: Session, tai_khoan_id: int) -> TaiKhoanNH:
    """Lookup TK NH; nếu không tồn tại → 400."""
    tk = db.get(TaiKhoanNH, tai_khoan_id)
    if not tk:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"tai_khoan_id={tai_khoan_id} không tồn tại",
        )
    return tk


def _tk_account_code(tk: TaiKhoanNH) -> str:
    """Map TaiKhoanNH.loai → account_code: 'tien_mat'→111, ngược lại 112."""
    if (tk.loai or "").strip() == "tien_mat":
        return "111"
    return "112"


def _insert_tknhgd(
    db: Session, *, tai_khoan_id: int, loai: str, ngay: date_cls,
    so_tien: Decimal, doi_tac: Optional[str], ghi_chu: Optional[str],
    source_app: str, source_doc_id: Optional[str], user: JWTPayload,
) -> TaiKhoanNHGiaoDich:
    gd = TaiKhoanNHGiaoDich(
        ngay=ngay, tai_khoan_id=tai_khoan_id, loai=loai, so_tien=so_tien,
        doi_tac=doi_tac, ghi_chu=ghi_chu,
        source_app=source_app, source_doc_id=source_doc_id,
        created_by=user.username,
    )
    db.add(gd)
    db.flush()
    return gd


# ─── VCSH endpoints ───────────────────────────────────────────────────────────

@router.get("", response_model=list[VonCSHOut])
def list_von_csh(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    from_date: Optional[date_cls] = Query(None, alias="from"),
    to_date: Optional[date_cls] = Query(None, alias="to"),
    loai: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = 0,
):
    stmt = select(VonCSH).order_by(VonCSH.ngay.desc(), VonCSH.id.desc())
    if from_date:
        stmt = stmt.where(VonCSH.ngay >= from_date)
    if to_date:
        stmt = stmt.where(VonCSH.ngay <= to_date)
    if loai:
        if loai not in _LOAI_VCSH:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"loai {loai!r} không hợp lệ",
            )
        stmt = stmt.where(VonCSH.loai_giao_dich == loai)
    stmt = stmt.limit(limit).offset(offset)
    items = db.execute(stmt).scalars().all()
    return [_serialize(v) for v in items]


@router.get("/summary", response_model=VonCSHSummary)
def summary(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Tổng VCSH + danh sách quỹ DN.

    von_gop_hien_tai = SUM(gop_von) - SUM(rut_von) (không trừ chia cổ tức / trích quỹ
    vì đó là phân phối lợi nhuận, không phải rút vốn — quy ước Papasan)
    """
    sums = db.execute(
        select(
            func.coalesce(
                func.sum(case((VonCSH.loai_giao_dich == "gop_von", VonCSH.so_tien), else_=0)),
                0,
            ).label("gop"),
            func.coalesce(
                func.sum(case((VonCSH.loai_giao_dich == "rut_von", VonCSH.so_tien), else_=0)),
                0,
            ).label("rut"),
            func.coalesce(
                func.sum(case((VonCSH.loai_giao_dich == "chia_co_tuc", VonCSH.so_tien), else_=0)),
                0,
            ).label("co_tuc"),
            func.coalesce(
                func.sum(case((VonCSH.loai_giao_dich == "trich_quy", VonCSH.so_tien), else_=0)),
                0,
            ).label("trich"),
            func.coalesce(
                func.sum(case((VonCSH.loai_giao_dich == "dieu_chinh", VonCSH.so_tien), else_=0)),
                0,
            ).label("dieu_chinh"),
        )
    ).one()

    quys = db.execute(
        select(QuyDN).where(QuyDN.active.is_(True)).order_by(QuyDN.ten_quy)
    ).scalars().all()

    return VonCSHSummary(
        tong_gop_von=Decimal(str(sums.gop or 0)),
        tong_rut_von=Decimal(str(sums.rut or 0)),
        tong_chia_co_tuc=Decimal(str(sums.co_tuc or 0)),
        tong_trich_quy=Decimal(str(sums.trich or 0)),
        tong_dieu_chinh=Decimal(str(sums.dieu_chinh or 0)),
        von_gop_hien_tai=Decimal(str(sums.gop or 0)) - Decimal(str(sums.rut or 0)),
        quy_dn=[
            {"id": q.id, "ten_quy": q.ten_quy, "so_du": q.so_du}
            for q in quys
        ],
    )


@router.post("/khoi-tao-ban-dau", response_model=VonCSHOut, status_code=status.HTTP_201_CREATED)
def khoi_tao_ban_dau(
    body: KhoiTaoBanDauBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Khởi tạo vốn ban đầu — chỉ chạy 1 lần.

    Chặn nếu đã có dòng `gop_von` trước đó → 409 Conflict.
    Ghi 1 dòng `gop_von` với ghi_chu='Vốn ban đầu'.
    """
    if user.role not in ("admin", "ceo"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Chỉ admin/ceo được khởi tạo vốn ban đầu",
        )

    existing = db.execute(
        select(VonCSH.id).where(VonCSH.loai_giao_dich == "gop_von").limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Đã có giao dịch góp vốn trước đó — không thể khởi tạo vốn ban đầu",
        )

    note = body.ghi_chu or "Vốn ban đầu"
    if "Vốn ban đầu" not in note:
        note = f"Vốn ban đầu — {note}"

    obj = _ghi_giao_dich(
        db, loai="gop_von", ngay=body.ngay, so_tien=body.so_tien,
        chu_so_huu=body.chu_so_huu, ghi_chu=note, user=user,
    )

    # Phase 2 — double-entry: nếu có tai_khoan_id → Nợ 112/111 (TK) / Có 411
    if body.tai_khoan_id:
        tk = _ensure_tk_nh(db, body.tai_khoan_id)
        gd = _insert_tknhgd(
            db, tai_khoan_id=tk.id, loai="thu", ngay=body.ngay,
            so_tien=body.so_tien, doi_tac=body.chu_so_huu,
            ghi_chu=f"Khởi tạo vốn ban đầu — {body.chu_so_huu or ''}",
            source_app="von_csh", source_doc_id=f"vcsh_{obj.id}", user=user,
        )
        db.add(SoQuy(
            ngay=body.ngay, loai="thu", so_tien=body.so_tien,
            tai_khoan=tk.ten_tk,
            noi_dung=f"Khởi tạo vốn ban đầu — {body.chu_so_huu or ''}",
            lien_quan="vcsh", ref_id=str(obj.id),
            phan_loai_cf="khac", created_by=user.username,
        ))
        post_journal(
            db,
            ngay=body.ngay, mo_ta=note, source_type="gop_von",
            source_id=str(obj.id), by_user=user.username,
            lines=[
                {"loai": "no", "account_code": _tk_account_code(tk),
                 "ref_table": "tai_khoan_nh", "ref_id": tk.id,
                 "so_tien": body.so_tien,
                 "ghi_chu": f"Nhận vốn ban đầu vào {tk.ten_tk}"},
                {"loai": "co", "account_code": "411",
                 "ref_table": "von_chu_so_huu", "ref_id": obj.id,
                 "so_tien": body.so_tien,
                 "ghi_chu": f"Vốn góp ban đầu — {body.chu_so_huu or ''}"},
            ],
        )

    db.commit()
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="vcsh_khoi_tao_ban_dau",
        user=user, request=request, resource=f"von_csh:{obj.id}",
        payload={"so_tien": float(body.so_tien), "ngay": str(body.ngay),
                 "tai_khoan_id": body.tai_khoan_id},
    )
    return _serialize(obj)


@router.post("/gop-von", response_model=VonCSHOut, status_code=status.HTTP_201_CREATED)
def gop_von(
    body: GopVonBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    _require_vcsh_admin(user)
    obj = _ghi_giao_dich(
        db, loai="gop_von", ngay=body.ngay, so_tien=body.so_tien,
        chu_so_huu=body.chu_so_huu, ghi_chu=body.ghi_chu,
        source_doc_id=body.source_doc_id, user=user,
    )
    if body.tai_khoan_id:
        tk = _ensure_tk_nh(db, body.tai_khoan_id)
        _insert_tknhgd(
            db, tai_khoan_id=tk.id, loai="thu", ngay=body.ngay,
            so_tien=body.so_tien, doi_tac=body.chu_so_huu,
            ghi_chu=f"Góp vốn — {body.chu_so_huu or ''}",
            source_app="von_csh", source_doc_id=f"vcsh_{obj.id}", user=user,
        )
        db.add(SoQuy(
            ngay=body.ngay, loai="thu", so_tien=body.so_tien,
            tai_khoan=tk.ten_tk,
            noi_dung=f"Góp vốn — {body.chu_so_huu or ''}",
            lien_quan="vcsh", ref_id=str(obj.id),
            phan_loai_cf="khac", created_by=user.username,
        ))
        post_journal(
            db,
            ngay=body.ngay, mo_ta=f"Góp vốn — {body.chu_so_huu or ''}",
            source_type="gop_von", source_id=str(obj.id), by_user=user.username,
            lines=[
                {"loai": "no", "account_code": _tk_account_code(tk),
                 "ref_table": "tai_khoan_nh", "ref_id": tk.id,
                 "so_tien": body.so_tien,
                 "ghi_chu": f"Nhận tiền góp vốn vào {tk.ten_tk}"},
                {"loai": "co", "account_code": "411",
                 "ref_table": "von_chu_so_huu", "ref_id": obj.id,
                 "so_tien": body.so_tien,
                 "ghi_chu": f"Vốn góp — {body.chu_so_huu or ''}"},
            ],
        )

    db.commit()
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="vcsh_gop_von",
        user=user, request=request, resource=f"von_csh:{obj.id}",
        payload={"so_tien": float(body.so_tien), "chu_so_huu": body.chu_so_huu,
                 "tai_khoan_id": body.tai_khoan_id},
    )
    return _serialize(obj)


@router.post("/chuyen-ln-thanh-von", response_model=VonCSHOut, status_code=status.HTTP_201_CREATED)
def chuyen_ln_thanh_von(
    body: GopVonBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Chuyển LN giữ lại → tăng vốn góp (capitalization of retained earnings).

    Bút toán: Nợ TK 421 (LN giữ lại) / Có TK 411 (Vốn góp).
    KHÔNG đụng tài khoản ngân hàng — chỉ chuyển trong VCSH.
    Tạo bản ghi loai='gop_von' với chu_so_huu hoặc ghi_chu chứa "(Chuyển từ LN giữ lại)".
    """
    _require_vcsh_admin(user)
    chu_so_huu = body.chu_so_huu or "DN"
    ghi_chu_full = f"Chuyển LN giữ lại thành vốn — {body.ghi_chu or ''}".strip(" —")

    obj = _ghi_giao_dich(
        db, loai="gop_von", ngay=body.ngay, so_tien=body.so_tien,
        chu_so_huu=chu_so_huu, ghi_chu=ghi_chu_full,
        source_doc_id=body.source_doc_id, user=user,
    )
    # KHÔNG insert tknhgd vì không có tiền chuyển vào TK NH
    # Journal: Nợ 421 / Có 411 (chuyển nội bộ trong VCSH)
    post_journal(
        db,
        ngay=body.ngay,
        mo_ta=f"Chuyển LN giữ lại → vốn góp — {chu_so_huu}",
        source_type="gop_von_tu_ln", source_id=str(obj.id), by_user=user.username,
        lines=[
            {"loai": "no", "account_code": "421",
             "ref_table": "von_chu_so_huu", "ref_id": obj.id,
             "so_tien": body.so_tien,
             "ghi_chu": "Giảm LN giữ lại"},
            {"loai": "co", "account_code": "411",
             "ref_table": "von_chu_so_huu", "ref_id": obj.id,
             "so_tien": body.so_tien,
             "ghi_chu": f"Tăng vốn góp — {chu_so_huu}"},
        ],
    )

    db.commit()
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="vcsh_chuyen_ln_thanh_von",
        user=user, request=request, resource=f"von_csh:{obj.id}",
        payload={"so_tien": float(body.so_tien), "chu_so_huu": chu_so_huu},
    )
    return _serialize(obj)


@router.post("/rut-von", response_model=VonCSHOut, status_code=status.HTTP_201_CREATED)
def rut_von(
    body: GopVonBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    _require_vcsh_admin(user)
    obj = _ghi_giao_dich(
        db, loai="rut_von", ngay=body.ngay, so_tien=body.so_tien,
        chu_so_huu=body.chu_so_huu, ghi_chu=body.ghi_chu,
        source_doc_id=body.source_doc_id, user=user,
    )
    if body.tai_khoan_id:
        tk = _ensure_tk_nh(db, body.tai_khoan_id)
        _assert_du_chi(db, tk.ten_tk, body.so_tien)  # chặn rút làm số dư âm
        _insert_tknhgd(
            db, tai_khoan_id=tk.id, loai="chi", ngay=body.ngay,
            so_tien=body.so_tien, doi_tac=body.chu_so_huu,
            ghi_chu=f"Rút vốn — {body.chu_so_huu or ''}",
            source_app="von_csh", source_doc_id=f"vcsh_{obj.id}", user=user,
        )
        db.add(SoQuy(
            ngay=body.ngay, loai="chi", so_tien=body.so_tien,
            tai_khoan=tk.ten_tk,
            noi_dung=f"Rút vốn — {body.chu_so_huu or ''}",
            lien_quan="vcsh", ref_id=str(obj.id),
            phan_loai_cf="khac", created_by=user.username,
        ))
        post_journal(
            db,
            ngay=body.ngay, mo_ta=f"Rút vốn — {body.chu_so_huu or ''}",
            source_type="rut_von", source_id=str(obj.id), by_user=user.username,
            lines=[
                {"loai": "no", "account_code": "411",
                 "ref_table": "von_chu_so_huu", "ref_id": obj.id,
                 "so_tien": body.so_tien,
                 "ghi_chu": f"Rút vốn — {body.chu_so_huu or ''}"},
                {"loai": "co", "account_code": _tk_account_code(tk),
                 "ref_table": "tai_khoan_nh", "ref_id": tk.id,
                 "so_tien": body.so_tien,
                 "ghi_chu": f"Chi tiền rút vốn từ {tk.ten_tk}"},
            ],
        )

    db.commit()
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="vcsh_rut_von",
        user=user, request=request, resource=f"von_csh:{obj.id}",
        payload={"so_tien": float(body.so_tien), "chu_so_huu": body.chu_so_huu,
                 "tai_khoan_id": body.tai_khoan_id},
    )
    return _serialize(obj)


@router.post("/chia-co-tuc", response_model=VonCSHOut, status_code=status.HTTP_201_CREATED)
def chia_co_tuc(
    body: GopVonBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    _require_vcsh_admin(user)
    obj = _ghi_giao_dich(
        db, loai="chia_co_tuc", ngay=body.ngay, so_tien=body.so_tien,
        chu_so_huu=body.chu_so_huu, ghi_chu=body.ghi_chu,
        source_doc_id=body.source_doc_id, user=user,
    )
    if body.tai_khoan_id:
        tk = _ensure_tk_nh(db, body.tai_khoan_id)
        _assert_du_chi(db, tk.ten_tk, body.so_tien)  # chặn chia cổ tức làm số dư âm
        _insert_tknhgd(
            db, tai_khoan_id=tk.id, loai="chi", ngay=body.ngay,
            so_tien=body.so_tien, doi_tac=body.chu_so_huu,
            ghi_chu=f"Chia cổ tức — {body.chu_so_huu or ''}",
            source_app="von_csh", source_doc_id=f"vcsh_{obj.id}", user=user,
        )
        db.add(SoQuy(
            ngay=body.ngay, loai="chi", so_tien=body.so_tien,
            tai_khoan=tk.ten_tk,
            noi_dung=f"Chia cổ tức — {body.chu_so_huu or ''}",
            lien_quan="vcsh", ref_id=str(obj.id),
            phan_loai_cf="khac", created_by=user.username,
        ))
        post_journal(
            db,
            ngay=body.ngay, mo_ta=f"Chia cổ tức — {body.chu_so_huu or ''}",
            source_type="chia_co_tuc", source_id=str(obj.id),
            by_user=user.username,
            lines=[
                {"loai": "no", "account_code": "421",
                 "ref_table": "von_chu_so_huu", "ref_id": obj.id,
                 "so_tien": body.so_tien,
                 "ghi_chu": f"Chia cổ tức — {body.chu_so_huu or ''}"},
                {"loai": "co", "account_code": _tk_account_code(tk),
                 "ref_table": "tai_khoan_nh", "ref_id": tk.id,
                 "so_tien": body.so_tien,
                 "ghi_chu": f"Chi tiền cổ tức từ {tk.ten_tk}"},
            ],
        )

    db.commit()
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="vcsh_chia_co_tuc",
        user=user, request=request, resource=f"von_csh:{obj.id}",
        payload={"so_tien": float(body.so_tien), "chu_so_huu": body.chu_so_huu,
                 "tai_khoan_id": body.tai_khoan_id},
    )
    return _serialize(obj)


@router.post("/trich-quy", response_model=VonCSHOut, status_code=status.HTTP_201_CREATED)
def trich_quy(
    body: TrichQuyBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Trích quỹ — phải kèm quy_id (active). Đồng thời cộng vào quy_dn.so_du.

    Phase 2: post journal Nợ 421 / Có 414|415|353 (theo tên quỹ).
    """
    _require_vcsh_admin(user)
    quy = db.get(QuyDN, body.quy_id)
    if not quy or not quy.active:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Quỹ id={body.quy_id} không tồn tại hoặc không active",
        )
    obj = _ghi_giao_dich(
        db, loai="trich_quy", ngay=body.ngay, so_tien=body.so_tien,
        chu_so_huu=body.chu_so_huu, ghi_chu=body.ghi_chu,
        source_doc_id=body.source_doc_id, quy_id=body.quy_id, user=user,
    )
    # Audit trail qua bảng quy_dn_giao_dich (thay cho direct UPDATE so_du)
    _nap_quy_dn(
        db,
        quy_id=quy.id,
        so_tien=body.so_tien,
        ngay=body.ngay,
        noi_dung=f"Trích quỹ {quy.ten_quy} từ LN giữ lại",
        source_type="trich_quy",
        source_id=str(obj.id),
        ghi_chu=body.ghi_chu,
        by_user=user.username,
    )

    quy_acc = map_quy_to_account(quy.ten_quy)
    post_journal(
        db,
        ngay=body.ngay, mo_ta=f"Trích quỹ {quy.ten_quy}",
        source_type="trich_quy", source_id=str(obj.id), by_user=user.username,
        lines=[
            {"loai": "no", "account_code": "421",
             "ref_table": "von_chu_so_huu", "ref_id": obj.id,
             "so_tien": body.so_tien,
             "ghi_chu": f"Trích từ LN giữ lại sang {quy.ten_quy}"},
            {"loai": "co", "account_code": quy_acc,
             "ref_table": "quy_dn", "ref_id": quy.id,
             "so_tien": body.so_tien,
             "ghi_chu": f"Tăng {quy.ten_quy}"},
        ],
    )

    db.commit()
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="vcsh_trich_quy",
        user=user, request=request, resource=f"von_csh:{obj.id}",
        payload={
            "so_tien": float(body.so_tien),
            "quy_id": body.quy_id, "ten_quy": quy.ten_quy,
            "account_code": quy_acc,
        },
    )
    return _serialize(obj)


@router.delete("/{vid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_von_csh(
    vid: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Xoá 1 dòng giao dịch VCSH (admin only).

    Nếu là `trich_quy` → hoàn lại quỹ (trừ quy_dn.so_du).
    """
    if user.role not in ("admin", "ceo"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Chỉ admin/ceo được xoá giao dịch VCSH",
        )
    obj = db.get(VonCSH, vid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "VonCSH không tồn tại")

    # Undo trich_quy — void giao dịch tương ứng trong quy_dn_giao_dich (đảo so_du)
    if obj.loai_giao_dich == "trich_quy" and obj.quy_id:
        from ..models import QuyDNGiaoDich
        gds = db.execute(
            select(QuyDNGiaoDich).where(
                QuyDNGiaoDich.quy_id == obj.quy_id,
                QuyDNGiaoDich.source_type == "trich_quy",
                QuyDNGiaoDich.source_id == str(obj.id),
            )
        ).scalars().all()
        for gd in gds:
            _void_quy_gd(db, gd.id, by_user=user.username)
        # Fallback: nếu không tìm thấy giao dịch (data cũ pre-Q2) → trừ trực tiếp
        if not gds:
            quy = db.get(QuyDN, obj.quy_id)
            if quy:
                quy.so_du = max(
                    Decimal("0"),
                    Decimal(str(quy.so_du or 0)) - Decimal(obj.so_tien),
                )

    payload = {
        "loai": obj.loai_giao_dich,
        "so_tien": float(obj.so_tien),
        "ngay": str(obj.ngay),
    }
    db.delete(obj)
    db.commit()
    log_action(
        db, app="ketoan", action="vcsh_delete",
        user=user, request=request, resource=f"von_csh:{vid}",
        payload=payload,
    )


# ─── Quỹ DN endpoints ────────────────────────────────────────────────────────

@quy_router.get("", response_model=list[QuyDNOut])
def list_quy_dn(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    active_only: bool = True,
):
    stmt = select(QuyDN).order_by(QuyDN.ten_quy)
    if active_only:
        stmt = stmt.where(QuyDN.active.is_(True))
    return db.execute(stmt).scalars().all()


@quy_router.post("", response_model=QuyDNOut, status_code=status.HTTP_201_CREATED)
def create_quy_dn(
    body: QuyDNCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    if user.role not in ("admin", "ceo", "manager", "kt"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền tạo quỹ")
    obj = QuyDN(**body.model_dump(exclude_unset=True))
    db.add(obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Tên quỹ {body.ten_quy!r} đã tồn tại",
        )
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="quy_dn_create",
        user=user, request=request, resource=f"quy_dn:{obj.id}",
        payload={"ten_quy": obj.ten_quy},
    )
    return obj


@quy_router.put("/{qid}", response_model=QuyDNOut)
def update_quy_dn(
    qid: int,
    body: QuyDNUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(QuyDN, qid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "QuyDN không tồn tại")
    fields = body.model_dump(exclude_unset=True)
    for k, v in fields.items():
        setattr(obj, k, v)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Tên quỹ trùng")
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="quy_dn_update",
        user=user, request=request, resource=f"quy_dn:{qid}",
        payload=fields,
    )
    return obj
