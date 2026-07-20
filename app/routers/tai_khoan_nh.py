"""TaiKhoanNH API — CRUD tài khoản ngân hàng / tiền mặt."""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import TaiKhoanNH
from ..schemas import TaiKhoanNHCreate, TaiKhoanNHUpdate, TaiKhoanNHOut
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


@router.get("", response_model=list[TaiKhoanNHOut])
def list_tai_khoan(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    active_only: bool = True,
    loai: Optional[str] = None,
):
    stmt = select(TaiKhoanNH).order_by(TaiKhoanNH.ten_tk)
    if active_only:
        stmt = stmt.where(TaiKhoanNH.active.is_(True))
    if loai:
        stmt = stmt.where(TaiKhoanNH.loai == loai)
    return db.execute(stmt).scalars().all()


@router.post("", response_model=TaiKhoanNHOut, status_code=status.HTTP_201_CREATED)
def create_tai_khoan(
    body: TaiKhoanNHCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    if body.so_tk:
        existing = db.execute(
            select(TaiKhoanNH).where(TaiKhoanNH.so_tk == body.so_tk)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Số tài khoản {body.so_tk} đã tồn tại"
            )
    obj = TaiKhoanNH(**body.model_dump(exclude_unset=True))
    db.add(obj)
    db.commit()
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="create_tai_khoan", user=user, request=request,
        resource=f"tai_khoan_nh:{obj.id}", payload={"ten_tk": obj.ten_tk},
    )
    return obj


@router.put("/{rid}", response_model=TaiKhoanNHOut)
def update_tai_khoan(
    rid: int,
    body: TaiKhoanNHUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(TaiKhoanNH, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "TaiKhoanNH không tồn tại")
    fields = body.model_dump(exclude_unset=True)
    for k, v in fields.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="update_tai_khoan", user=user, request=request,
        resource=f"tai_khoan_nh:{rid}", payload=fields,
    )
    return obj


@router.delete("/{rid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tai_khoan(
    rid: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(TaiKhoanNH, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "TaiKhoanNH không tồn tại")
    db.delete(obj)
    db.commit()
    log_action(
        db, app="ketoan", action="delete_tai_khoan", user=user, request=request,
        resource=f"tai_khoan_nh:{rid}",
    )
