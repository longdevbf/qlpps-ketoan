"""ChiPhiCoDinh API — CRUD + nhom_chi_phi.

Sprint M3 (2026-04-28): thêm `nhom_chi_phi` để phục vụ P&L.
"""
from datetime import date as date_cls
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import (
    ChiPhiCoDinh, CongNo, LoaiChiPhi, TaiKhoanNH, TaiKhoanNHGiaoDich,
)
from ..schemas import CoDinhCreate, CoDinhOut, CoDinhUpdate
from ..schemas.co_dinh import VALID_PHUONG_PHAP_PHAN_BO
from ..services.journal import post_journal
from ._deps import require_ketoan_user


_NHOM_TO_ACCOUNT = {
    "ban_hang": "641",
    "quan_ly": "642",
    "tai_chinh": "635",
    "khac": "811",
}


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


VALID_NHOM = {"ban_hang", "quan_ly", "tai_chinh", "khac"}


def _resolve_nhom(db: Session, loai: Optional[str], nhom: Optional[str]) -> str:
    if nhom and nhom in VALID_NHOM:
        return nhom
    if loai:
        row = db.execute(
            select(LoaiChiPhi.nhom_default).where(LoaiChiPhi.ten == loai)
        ).scalar_one_or_none()
        if row and row in VALID_NHOM:
            return row
    return "khac"


@router.get("", response_model=list[CoDinhOut])
def list_co_dinh(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu_thang: Optional[date_cls] = Query(None, description="lọc thang_bat_dau >="),
    den_thang: Optional[date_cls] = Query(None, description="lọc thang_bat_dau <="),
    loai_chi_phi: Optional[str] = None,
    lap_lai: Optional[bool] = None,
    nhom: Optional[str] = Query(None, description="ban_hang|quan_ly|tai_chinh|khac"),
    da_phan_bo: Optional[bool] = Query(
        None, description="True → chỉ dòng phân bổ đa kỳ (so_thang_phan_bo > 1)"
    ),
    phuong_phap: Optional[str] = Query(
        None,
        description=(
            "Phase 5C — filter theo phương pháp phân bổ: "
            "duong_thang|prorated_by_day|front_loaded|seasonal|by_revenue_pct|manual"
        ),
    ),
    limit: int = 500,
    offset: int = 0,
):
    stmt = select(ChiPhiCoDinh).order_by(
        ChiPhiCoDinh.thang_bat_dau.desc(), ChiPhiCoDinh.id.desc()
    )
    if tu_thang:
        stmt = stmt.where(ChiPhiCoDinh.thang_bat_dau >= tu_thang)
    if den_thang:
        stmt = stmt.where(ChiPhiCoDinh.thang_bat_dau <= den_thang)
    if loai_chi_phi:
        stmt = stmt.where(ChiPhiCoDinh.loai_chi_phi == loai_chi_phi)
    if lap_lai is not None:
        stmt = stmt.where(ChiPhiCoDinh.lap_lai == lap_lai)
    if nhom:
        if nhom not in VALID_NHOM:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"nhom phải thuộc {sorted(VALID_NHOM)}")
        stmt = stmt.where(ChiPhiCoDinh.nhom_chi_phi == nhom)
    if da_phan_bo is True:
        stmt = stmt.where(ChiPhiCoDinh.so_thang_phan_bo > 1)
    elif da_phan_bo is False:
        stmt = stmt.where(ChiPhiCoDinh.so_thang_phan_bo == 1)
    if phuong_phap:
        if phuong_phap not in VALID_PHUONG_PHAP_PHAN_BO:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"phuong_phap phải thuộc {sorted(VALID_PHUONG_PHAP_PHAN_BO)}",
            )
        stmt = stmt.where(ChiPhiCoDinh.phuong_phap_phan_bo == phuong_phap)
    stmt = stmt.limit(limit).offset(offset)
    return db.execute(stmt).scalars().all()


@router.post("", response_model=CoDinhOut, status_code=status.HTTP_201_CREATED)
def create_co_dinh(
    body: CoDinhCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    fields = body.model_dump(exclude_unset=True)
    fields["nhom_chi_phi"] = _resolve_nhom(
        db, fields.get("loai_chi_phi"), fields.get("nhom_chi_phi"),
    )
    tai_khoan_id = fields.pop("tai_khoan_id", None)
    cong_no_ncc_id = fields.pop("cong_no_ncc_id", None)

    # Phase 5B — fallback ngay_bat_dau ← thang_bat_dau nếu user không truyền
    if not fields.get("ngay_bat_dau") and fields.get("thang_bat_dau"):
        fields["ngay_bat_dau"] = fields["thang_bat_dau"]

    obj = ChiPhiCoDinh(**fields, created_by=user.username)
    db.add(obj)
    db.flush()

    # Phase 2 — Double-entry posting (đối với 1 kỳ — so_tien_thang)
    nhom = obj.nhom_chi_phi or "khac"
    cp_account = _NHOM_TO_ACCOUNT.get(nhom, "811")
    so_tien = Decimal(str(obj.so_tien_thang or 0))

    if so_tien > 0 and tai_khoan_id:
        tk = db.get(TaiKhoanNH, tai_khoan_id)
        if not tk:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"tai_khoan_id={tai_khoan_id} không tồn tại",
            )
        cash_acc = "111" if (tk.loai or "").strip() == "tien_mat" else "112"
        gd = TaiKhoanNHGiaoDich(
            ngay=obj.thang_bat_dau, tai_khoan_id=tk.id, loai="chi",
            so_tien=so_tien, ghi_chu=f"Chi phí cố định — {obj.mo_ta or ''}",
            source_app="co_dinh", source_doc_id=f"co_dinh_{obj.id}",
            created_by=user.username,
        )
        db.add(gd)
        db.flush()
        post_journal(
            db, ngay=obj.thang_bat_dau,
            mo_ta=f"Chi phí cố định {obj.loai_chi_phi or ''} — TT bằng {tk.ten_tk}",
            source_type="chi_phi_co_dinh", source_id=str(obj.id),
            by_user=user.username,
            lines=[
                {"loai": "no", "account_code": cp_account,
                 "ref_table": "chi_phi_co_dinh", "ref_id": obj.id,
                 "so_tien": so_tien,
                 "ghi_chu": f"{nhom} — {obj.loai_chi_phi or ''}"},
                {"loai": "co", "account_code": cash_acc,
                 "ref_table": "tai_khoan_nh", "ref_id": tk.id,
                 "so_tien": so_tien, "ghi_chu": f"Chi từ {tk.ten_tk}"},
            ],
        )
    elif so_tien > 0 and cong_no_ncc_id:
        cn = db.get(CongNo, cong_no_ncc_id)
        if not cn:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"cong_no_ncc_id={cong_no_ncc_id!r} không tồn tại",
            )
        post_journal(
            db, ngay=obj.thang_bat_dau,
            mo_ta=f"Chi phí cố định {obj.loai_chi_phi or ''} — ghi nhận phải trả",
            source_type="chi_phi_co_dinh", source_id=str(obj.id),
            by_user=user.username,
            lines=[
                {"loai": "no", "account_code": cp_account,
                 "ref_table": "chi_phi_co_dinh", "ref_id": obj.id,
                 "so_tien": so_tien,
                 "ghi_chu": f"{nhom} — {obj.loai_chi_phi or ''}"},
                {"loai": "co", "account_code": "331",
                 "ref_table": "cong_no", "ref_id": None,
                 "so_tien": so_tien, "ghi_chu": f"Phải trả NCC ({cn.id})"},
            ],
        )

    db.commit()
    db.refresh(obj)
    # Invalidate PL cache (Phase 4 — phân bổ định phí)
    try:
        from .bao_cao_pnl import invalidate_pl_cache
        invalidate_pl_cache()
    except Exception:
        pass
    log_action(
        db, app="ketoan", action="create_co_dinh", user=user, request=request,
        resource=f"co_dinh:{obj.id}",
        payload={"thang": str(obj.thang_bat_dau), "so_tien": str(obj.so_tien_thang),
                 "nhom": obj.nhom_chi_phi,
                 "so_thang_phan_bo": obj.so_thang_phan_bo,
                 "phuong_phap_phan_bo": obj.phuong_phap_phan_bo,
                 "tai_khoan_id": tai_khoan_id,
                 "cong_no_ncc_id": cong_no_ncc_id},
    )
    return obj


@router.get("/{rid}", response_model=CoDinhOut)
def get_co_dinh(
    rid: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(ChiPhiCoDinh, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CoDinh không tồn tại")
    return obj


@router.put("/{rid}", response_model=CoDinhOut)
def update_co_dinh(
    rid: int,
    body: CoDinhUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(ChiPhiCoDinh, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CoDinh không tồn tại")
    fields = body.model_dump(exclude_unset=True)
    if "loai_chi_phi" in fields and "nhom_chi_phi" not in fields:
        fields["nhom_chi_phi"] = _resolve_nhom(db, fields["loai_chi_phi"], None)
    if "nhom_chi_phi" in fields and fields["nhom_chi_phi"] not in VALID_NHOM:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"nhom_chi_phi phải thuộc {sorted(VALID_NHOM)}"
        )
    for k, v in fields.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    try:
        from .bao_cao_pnl import invalidate_pl_cache
        invalidate_pl_cache()
    except Exception:
        pass
    log_action(
        db, app="ketoan", action="update_co_dinh", user=user, request=request,
        resource=f"co_dinh:{rid}", payload=fields,
    )
    return obj


@router.delete("/{rid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_co_dinh(
    rid: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(ChiPhiCoDinh, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CoDinh không tồn tại")
    db.delete(obj)
    db.commit()
    try:
        from .bao_cao_pnl import invalidate_pl_cache
        invalidate_pl_cache()
    except Exception:
        pass
    log_action(
        db, app="ketoan", action="delete_co_dinh", user=user, request=request,
        resource=f"co_dinh:{rid}",
    )
