"""Phase 3 — Tài Sản Cố Định + Khấu Hao (Router).

Endpoints:
    GET    /api/tai-san                   ?loai=&nhom=&trang_thai=&q=
    GET    /api/tai-san/summary           summary by loại/nhóm/bộ phận
    GET    /api/tai-san/khau-hao/lich-su  ?tscd_id=
    GET    /api/tai-san/khau-hao/{thang}  list khau_hao_log tháng đó
    POST   /api/tai-san/khau-hao/{thang}  chạy khấu hao tháng (admin/kt)
    GET    /api/tai-san/{id}              detail + lịch sử khấu hao
    POST   /api/tai-san                   tạo + auto post JE mua nếu có TK
    PUT    /api/tai-san/{id}              sửa info (chặn nguyen_gia/so_thang_kh
                                          nếu đã có khau_hao_log)
    POST   /api/tai-san/{id}/thanh-ly     thanh lý + post JE
    DELETE /api/tai-san/{id}              chặn nếu có khau_hao_log
                                          (admin/ceo only — hard delete)
"""
from datetime import date as date_cls
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import KhauHaoLog, TaiKhoanNH, TaiSanCoDinh
from ..schemas import (
    ChayKhauHaoResponse, KhauHaoLogOut, ThanhLyBody,
    TSCDCreate, TSCDDetailOut, TSCDOut, TSCDSummary, TSCDSummaryGroup,
    TSCDUpdate,
)
from ..services.tscd_calc import (
    chay_khau_hao_thang, mua_tscd, next_ma_tscd, thanh_ly_tscd,
)
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _to_dec(x) -> Decimal:
    if x is None:
        return Decimal("0")
    return x if isinstance(x, Decimal) else Decimal(str(x))


def _serialize(t: TaiSanCoDinh, db: Session, *, with_logs: bool = False) -> dict:
    nguyen_gia = _to_dec(t.nguyen_gia)
    hao_mon = _to_dec(t.hao_mon_luy_ke)
    con_lai = nguyen_gia - hao_mon
    so_tien_thang = (
        nguyen_gia / Decimal(t.so_thang_kh)
        if t.so_thang_kh else Decimal("0")
    )
    n_logs = db.execute(
        select(func.count(KhauHaoLog.id))
        .where(KhauHaoLog.tscd_id == t.id)
    ).scalar() or 0

    base = {
        "id": t.id,
        "ma_tscd": t.ma_tscd,
        "ten_tscd": t.ten_tscd,
        "loai": t.loai,
        "nhom": t.nhom,
        "ngay_mua": t.ngay_mua,
        "ngay_su_dung": t.ngay_su_dung,
        "nguyen_gia": nguyen_gia,
        "chi_phi_lap_dat": _to_dec(t.chi_phi_lap_dat),
        "so_thang_kh": t.so_thang_kh,
        "phuong_phap": t.phuong_phap,
        "hao_mon_luy_ke": hao_mon,
        "account_code": t.account_code,
        "bo_phan": t.bo_phan,
        "ncc": t.ncc,
        "source_doc_id": t.source_doc_id,
        "trang_thai": t.trang_thai,
        "ngay_thanh_ly": t.ngay_thanh_ly,
        "gia_thanh_ly": t.gia_thanh_ly,
        "ghi_chu": t.ghi_chu,
        "hinh_anh": t.hinh_anh,
        "created_by": t.created_by,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "gia_tri_con_lai": con_lai,
        "so_tien_kh_thang": so_tien_thang.quantize(Decimal("0.01")),
        "so_thang_da_kh": int(n_logs),
    }
    if with_logs:
        logs = db.execute(
            select(KhauHaoLog)
            .where(KhauHaoLog.tscd_id == t.id)
            .order_by(KhauHaoLog.thang)
        ).scalars().all()
        base["khau_hao_logs"] = [
            {
                "id": l.id, "tscd_id": l.tscd_id, "thang": l.thang,
                "so_tien": l.so_tien,
                "hao_mon_luy_ke_sau": l.hao_mon_luy_ke_sau,
                "journal_id": l.journal_id,
                "ghi_chu": l.ghi_chu, "created_by": l.created_by,
                "created_at": l.created_at,
            }
            for l in logs
        ]
    return base


def _has_khau_hao(db: Session, tscd_id: int) -> bool:
    return bool(db.execute(
        select(KhauHaoLog.id).where(KhauHaoLog.tscd_id == tscd_id).limit(1)
    ).scalar())


# ─── List + Summary ───────────────────────────────────────────────────────────

@router.get("", response_model=list[dict])
def list_tscd(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    loai: Optional[str] = Query(None, pattern=r"^(huu_hinh|vo_hinh)$"),
    nhom: Optional[str] = None,
    trang_thai: Optional[str] = Query(
        None, pattern=r"^(dang_su_dung|da_thanh_ly|hong)$"
    ),
    bo_phan: Optional[str] = Query(
        None, pattern=r"^(ban_hang|quan_ly|tai_chinh|khac)$"
    ),
    q: Optional[str] = Query(None, description="Search ma_tscd / ten_tscd / ncc"),
):
    stmt = select(TaiSanCoDinh).order_by(
        TaiSanCoDinh.trang_thai, TaiSanCoDinh.id.desc()
    )
    if loai:
        stmt = stmt.where(TaiSanCoDinh.loai == loai)
    if nhom:
        stmt = stmt.where(TaiSanCoDinh.nhom == nhom)
    if trang_thai:
        stmt = stmt.where(TaiSanCoDinh.trang_thai == trang_thai)
    if bo_phan:
        stmt = stmt.where(TaiSanCoDinh.bo_phan == bo_phan)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            (TaiSanCoDinh.ma_tscd.ilike(like))
            | (TaiSanCoDinh.ten_tscd.ilike(like))
            | (TaiSanCoDinh.ncc.ilike(like))
        )
    rows = db.execute(stmt).scalars().all()
    return [_serialize(t, db) for t in rows]


@router.get("/summary", response_model=TSCDSummary)
def summary(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    only_active: bool = Query(
        True, description="True=chỉ tính trang_thai='dang_su_dung'",
    ),
):
    """Tổng hợp TSCĐ — tổng nguyên giá, hao mòn, còn lại + group by."""
    base_filter = []
    if only_active:
        base_filter.append(TaiSanCoDinh.trang_thai == "dang_su_dung")

    # Counts theo trang_thai
    counts = dict(
        db.execute(
            select(TaiSanCoDinh.trang_thai, func.count(TaiSanCoDinh.id))
            .group_by(TaiSanCoDinh.trang_thai)
        ).all()
    )

    # Tổng (theo filter)
    totals = db.execute(
        select(
            func.coalesce(func.sum(TaiSanCoDinh.nguyen_gia), 0),
            func.coalesce(func.sum(TaiSanCoDinh.hao_mon_luy_ke), 0),
        ).where(*base_filter)
    ).one()
    tong_ng = _to_dec(totals[0])
    tong_hm = _to_dec(totals[1])

    def _group(field) -> list[TSCDSummaryGroup]:
        rows = db.execute(
            select(
                field,
                func.coalesce(func.sum(TaiSanCoDinh.nguyen_gia), 0).label("ng"),
                func.coalesce(func.sum(TaiSanCoDinh.hao_mon_luy_ke), 0).label("hm"),
                func.count(TaiSanCoDinh.id).label("n"),
            ).where(*base_filter).group_by(field).order_by(field)
        ).all()
        out: list[TSCDSummaryGroup] = []
        for k, ng, hm, n in rows:
            ng_d = _to_dec(ng)
            hm_d = _to_dec(hm)
            out.append(TSCDSummaryGroup(
                key=str(k or ""),
                nguyen_gia=ng_d,
                hao_mon_luy_ke=hm_d,
                gia_tri_con_lai=ng_d - hm_d,
                n_tscd=int(n or 0),
            ))
        return out

    return TSCDSummary(
        tong_nguyen_gia=tong_ng,
        tong_hao_mon=tong_hm,
        tong_con_lai=tong_ng - tong_hm,
        n_dang_su_dung=int(counts.get("dang_su_dung", 0) or 0),
        n_da_thanh_ly=int(counts.get("da_thanh_ly", 0) or 0),
        n_hong=int(counts.get("hong", 0) or 0),
        by_loai=_group(TaiSanCoDinh.loai),
        by_nhom=_group(TaiSanCoDinh.nhom),
        by_bo_phan=_group(TaiSanCoDinh.bo_phan),
    )


# ─── Khấu hao endpoints (đặt TRƯỚC /{id} để không bị catch-all) ──────────────

@router.get("/khau-hao/lich-su")
def lich_su_khau_hao(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tscd_id: Optional[int] = Query(None, gt=0),
    limit: int = Query(500, ge=1, le=5000),
):
    """Lịch sử khấu hao toàn bộ (hoặc 1 TSCĐ nếu có `tscd_id`)."""
    stmt = (
        select(KhauHaoLog, TaiSanCoDinh.ma_tscd, TaiSanCoDinh.ten_tscd,
               TaiSanCoDinh.nhom, TaiSanCoDinh.bo_phan)
        .join(TaiSanCoDinh, TaiSanCoDinh.id == KhauHaoLog.tscd_id)
        .order_by(KhauHaoLog.thang.desc(), KhauHaoLog.tscd_id)
        .limit(limit)
    )
    if tscd_id:
        stmt = stmt.where(KhauHaoLog.tscd_id == tscd_id)
    rows = db.execute(stmt).all()
    return [
        {
            "id": l.id, "tscd_id": l.tscd_id, "thang": l.thang,
            "so_tien": l.so_tien,
            "hao_mon_luy_ke_sau": l.hao_mon_luy_ke_sau,
            "journal_id": l.journal_id, "ghi_chu": l.ghi_chu,
            "created_by": l.created_by, "created_at": l.created_at,
            "ma_tscd": ma, "ten_tscd": ten, "nhom": nhom, "bo_phan": bp,
        }
        for l, ma, ten, nhom, bp in rows
    ]


@router.get("/khau-hao/{thang}")
def get_khau_hao_thang(
    thang: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """List khau_hao_log của tháng `YYYY-MM` (kèm ma/ten TSCĐ)."""
    import re
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", thang):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"thang phải dạng YYYY-MM, nhận: {thang!r}",
        )
    rows = db.execute(
        select(
            KhauHaoLog, TaiSanCoDinh.ma_tscd, TaiSanCoDinh.ten_tscd,
            TaiSanCoDinh.nhom, TaiSanCoDinh.bo_phan,
        )
        .join(TaiSanCoDinh, TaiSanCoDinh.id == KhauHaoLog.tscd_id)
        .where(KhauHaoLog.thang == thang)
        .order_by(TaiSanCoDinh.id)
    ).all()
    items = []
    tong = Decimal("0")
    for l, ma, ten, nhom, bp in rows:
        tong += _to_dec(l.so_tien)
        items.append({
            "id": l.id, "tscd_id": l.tscd_id, "thang": l.thang,
            "so_tien": l.so_tien,
            "hao_mon_luy_ke_sau": l.hao_mon_luy_ke_sau,
            "journal_id": l.journal_id, "ghi_chu": l.ghi_chu,
            "created_by": l.created_by, "created_at": l.created_at,
            "ma_tscd": ma, "ten_tscd": ten, "nhom": nhom, "bo_phan": bp,
        })
    return {"thang": thang, "tong_kh": tong, "items": items, "n": len(items)}


@router.post("/khau-hao/{thang}", response_model=ChayKhauHaoResponse)
def post_khau_hao_thang(
    thang: str, request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Chạy khấu hao tháng — admin/kt only.

    Idempotent: TSCĐ đã có log tháng đó sẽ skip (ly_do=da_khau_hao).
    """
    if user.role not in ("admin", "ceo", "assistant_ceo", "manager", "kt"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Chỉ admin/kế toán được chạy khấu hao",
        )
    result = chay_khau_hao_thang(db, thang=thang, by_user=user.username)
    db.commit()
    log_action(
        db, app="ketoan", action="chay_khau_hao", user=user, request=request,
        resource=f"khau_hao:{thang}",
        payload={
            "thang": thang,
            "da_xu_ly": result["da_xu_ly"],
            "tong_kh": float(result["tong_kh"]),
        },
    )
    return result


# ─── CRUD — detail / create / update / delete ────────────────────────────────

@router.get("/{tscd_id}", response_model=TSCDDetailOut)
def get_tscd(
    tscd_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    t = db.execute(
        select(TaiSanCoDinh)
        .options(selectinload(TaiSanCoDinh.khau_hao_logs))
        .where(TaiSanCoDinh.id == tscd_id)
    ).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "TSCĐ không tồn tại")
    return _serialize(t, db, with_logs=True)


@router.post("", response_model=TSCDDetailOut, status_code=status.HTTP_201_CREATED)
def create_tscd(
    body: TSCDCreate, request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    if user.role not in ("admin", "ceo", "assistant_ceo", "manager", "kt"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Không có quyền tạo TSCĐ",
        )

    if body.ngay_su_dung < body.ngay_mua:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "ngay_su_dung phải >= ngay_mua",
        )

    if body.chi_phi_lap_dat > body.nguyen_gia:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "chi_phi_lap_dat phải <= nguyen_gia (chi phí lắp đặt nằm trong nguyên giá)",
        )

    account_code = "213" if body.loai == "vo_hinh" else "211"

    t = TaiSanCoDinh(
        ma_tscd=next_ma_tscd(db),
        ten_tscd=body.ten_tscd,
        loai=body.loai,
        nhom=body.nhom,
        ngay_mua=body.ngay_mua,
        ngay_su_dung=body.ngay_su_dung,
        nguyen_gia=body.nguyen_gia,
        chi_phi_lap_dat=body.chi_phi_lap_dat,
        so_thang_kh=body.so_thang_kh,
        phuong_phap="duong_thang",
        hao_mon_luy_ke=Decimal("0"),
        account_code=account_code,
        bo_phan=body.bo_phan,
        ncc=body.ncc,
        source_doc_id=body.source_doc_id,
        trang_thai="dang_su_dung",
        ghi_chu=body.ghi_chu,
        hinh_anh=body.hinh_anh,
        created_by=user.username,
    )
    db.add(t)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Mã TSCĐ {t.ma_tscd!r} đã tồn tại",
        )

    # Auto post JE mua TSCĐ nếu có TK chi tiền
    if body.tai_khoan_id:
        mua_tscd(
            db, tscd=t, tai_khoan_id=body.tai_khoan_id,
            by_user=user.username,
        )

    db.commit()
    db.refresh(t)
    log_action(
        db, app="ketoan", action="create_tscd", user=user, request=request,
        resource=f"tscd:{t.id}",
        payload={
            "ma_tscd": t.ma_tscd, "ten_tscd": t.ten_tscd,
            "nguyen_gia": float(t.nguyen_gia),
            "so_thang_kh": t.so_thang_kh, "tai_khoan_id": body.tai_khoan_id,
        },
    )
    return _serialize(t, db, with_logs=True)


@router.put("/{tscd_id}", response_model=TSCDOut)
def update_tscd(
    tscd_id: int, body: TSCDUpdate, request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    if user.role not in ("admin", "ceo", "assistant_ceo", "manager", "kt"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền")
    t = db.get(TaiSanCoDinh, tscd_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "TSCĐ không tồn tại")

    fields = body.model_dump(exclude_unset=True)
    # Chặn sửa nguyen_gia / so_thang_kh nếu đã có khau_hao_log
    if ("nguyen_gia" in fields or "so_thang_kh" in fields) and _has_khau_hao(db, t.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Không được sửa nguyen_gia / so_thang_kh khi đã có khấu hao — "
            "huỷ các bút toán khấu hao trước nếu cần.",
        )

    # Sync account_code nếu đổi loai
    if "loai" in fields:
        new_loai = fields["loai"]
        fields["account_code"] = "213" if new_loai == "vo_hinh" else "211"

    for k, v in fields.items():
        setattr(t, k, v)

    if t.ngay_su_dung and t.ngay_mua and t.ngay_su_dung < t.ngay_mua:
        db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "ngay_su_dung phải >= ngay_mua",
        )

    if _to_dec(t.chi_phi_lap_dat) > _to_dec(t.nguyen_gia):
        db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "chi_phi_lap_dat phải <= nguyen_gia",
        )

    db.commit()
    db.refresh(t)
    log_action(
        db, app="ketoan", action="update_tscd", user=user, request=request,
        resource=f"tscd:{tscd_id}", payload=fields,
    )
    return _serialize(t, db)


@router.delete("/{tscd_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tscd(
    tscd_id: int, request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    if user.role not in ("admin", "ceo"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Chỉ admin/ceo được xoá TSCĐ",
        )
    t = db.get(TaiSanCoDinh, tscd_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "TSCĐ không tồn tại")
    if _has_khau_hao(db, tscd_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "TSCĐ đã có khấu hao — không xoá được. "
            "Hãy thanh lý hoặc đảo bút toán khấu hao trước.",
        )
    ma = t.ma_tscd
    db.delete(t)
    db.commit()
    log_action(
        db, app="ketoan", action="delete_tscd", user=user, request=request,
        resource=f"tscd:{tscd_id}", payload={"ma_tscd": ma},
    )


# ─── Thanh lý ─────────────────────────────────────────────────────────────────

@router.post("/{tscd_id}/thanh-ly", status_code=status.HTTP_201_CREATED)
def post_thanh_ly(
    tscd_id: int, body: ThanhLyBody, request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    if user.role not in ("admin", "ceo", "assistant_ceo", "manager", "kt"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền")
    je = thanh_ly_tscd(
        db,
        tscd_id=tscd_id,
        gia_thanh_ly=body.gia_thanh_ly,
        ngay=body.ngay_thanh_ly,
        tai_khoan_id=body.tai_khoan_id,
        ghi_chu=body.ghi_chu,
        by_user=user.username,
    )
    db.commit()
    log_action(
        db, app="ketoan", action="thanh_ly_tscd", user=user, request=request,
        resource=f"tscd:{tscd_id}",
        payload={
            "ngay": str(body.ngay_thanh_ly),
            "gia_thanh_ly": float(body.gia_thanh_ly),
            "tai_khoan_id": body.tai_khoan_id,
        },
    )
    return {
        "ok": True,
        "tscd_id": tscd_id,
        "journal_id": je.id,
        "ma_but_toan": je.ma_but_toan,
    }
