"""SoDuDauKy API — số dư đầu kỳ theo tháng × tài khoản (upsert)."""
from datetime import date as date_cls, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import SoDuDauKy, TaiKhoanNH
from ..schemas import SoDuDauKyCreate, SoDuDauKyOut
from ._deps import require_ketoan_user, require_ceo_thuchi


router = APIRouter()
_AUTH = Depends(require_ketoan_user)
# Số dư đầu kỳ = baseline Bảng Cân Đối + số dư TK → sửa/xoá 1 dòng dịch cả cân đối.
# Chỉ CEO/admin (đồng bộ von_csh + cong_no opening). (anh Quang 2026-08-31)
_CEO_EDIT = Depends(require_ceo_thuchi)


def _parse_thang_yyyy_mm(thang: str) -> date_cls:
    """Convert 'YYYY-MM' (or 'YYYY-MM-DD') → date(YYYY, MM, 1)."""
    try:
        if len(thang) == 7:                      # 'YYYY-MM'
            return datetime.strptime(thang + "-01", "%Y-%m-%d").date()
        return datetime.strptime(thang[:10], "%Y-%m-%d").date().replace(day=1)
    except ValueError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Tham số thang phải dạng YYYY-MM, nhận: {thang!r}",
        )


def _to_out(sd: SoDuDauKy, tk: TaiKhoanNH | None) -> SoDuDauKyOut:
    return SoDuDauKyOut(
        id=sd.id,
        thang=sd.thang,
        tai_khoan_id=sd.tai_khoan_id,
        so_du=sd.so_du,
        ghi_chu=sd.ghi_chu,
        created_at=sd.created_at,
        ten_tk=tk.ten_tk if tk else None,
        loai_tk=tk.loai if tk else None,
    )


@router.get("", response_model=list[SoDuDauKyOut])
def list_so_du_dau_ky(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    thang: str = Query(..., description="YYYY-MM"),
):
    """List số dư đầu kỳ tháng `thang`, kèm tên/loại tài khoản (left join)."""
    thang_date = _parse_thang_yyyy_mm(thang)
    rows = db.execute(
        select(SoDuDauKy, TaiKhoanNH)
        .join(TaiKhoanNH, TaiKhoanNH.id == SoDuDauKy.tai_khoan_id, isouter=True)
        .where(SoDuDauKy.thang == thang_date)
        .order_by(SoDuDauKy.id.asc())
    ).all()
    return [_to_out(sd, tk) for sd, tk in rows]


@router.post("", response_model=SoDuDauKyOut, status_code=status.HTTP_201_CREATED)
def upsert_so_du_dau_ky(
    body: SoDuDauKyCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _CEO_EDIT],
):
    """Upsert theo (thang, tai_khoan_id) — tháng phải là YYYY-MM-01."""
    # Normalize thang về day=1
    thang = body.thang.replace(day=1)

    existing = db.execute(
        select(SoDuDauKy).where(
            SoDuDauKy.thang == thang,
            SoDuDauKy.tai_khoan_id == body.tai_khoan_id,
        )
    ).scalar_one_or_none()

    action: str
    if existing:
        existing.so_du = body.so_du
        existing.ghi_chu = body.ghi_chu
        obj = existing
        action = "update_so_du_dau_ky"
    else:
        obj = SoDuDauKy(
            thang=thang,
            tai_khoan_id=body.tai_khoan_id,
            so_du=body.so_du,
            ghi_chu=body.ghi_chu,
        )
        db.add(obj)
        action = "create_so_du_dau_ky"

    db.commit()
    db.refresh(obj)

    tk = (
        db.get(TaiKhoanNH, obj.tai_khoan_id) if obj.tai_khoan_id is not None else None
    )

    log_action(
        db, app="ketoan", action=action, user=user, request=request,
        resource=f"so_du_dau_ky:{obj.id}",
        payload={
            "thang": str(obj.thang),
            "tai_khoan_id": obj.tai_khoan_id,
            "so_du": str(obj.so_du),
        },
    )
    return _to_out(obj, tk)


@router.delete("/{rid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_so_du_dau_ky(
    rid: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _CEO_EDIT],
):
    obj = db.get(SoDuDauKy, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SoDuDauKy không tồn tại")
    db.delete(obj)
    db.commit()
    log_action(
        db, app="ketoan", action="delete_so_du_dau_ky", user=user, request=request,
        resource=f"so_du_dau_ky:{rid}",
    )
