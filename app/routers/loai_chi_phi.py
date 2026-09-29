"""LoaiChiPhi API — CRUD danh mục loại chi phí."""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import ChiPhiCoDinh, ChiPhiPhatSinh, LoaiChiPhi
from ..schemas import LoaiChiPhiCreate, LoaiChiPhiUpdate, LoaiChiPhiOut
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


VALID_NHOM = {"ban_hang", "quan_ly", "tai_chinh", "khac"}


def _so_phieu_dung(db: Session, ten: str) -> int:
    """Số phiếu chi phí (phát sinh + cố định) đang gắn loại này — liên kết lỏng theo tên."""
    return sum(
        db.execute(select(func.count()).select_from(m).where(m.loai_chi_phi == ten)).scalar_one()
        for m in (ChiPhiPhatSinh, ChiPhiCoDinh)
    )


@router.get("", response_model=list[LoaiChiPhiOut])
def list_loai_chi_phi(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    active_only: bool = True,
    nhom: Optional[str] = None,
):
    stmt = select(LoaiChiPhi).order_by(LoaiChiPhi.ten)
    if active_only:
        stmt = stmt.where(LoaiChiPhi.active.is_(True))
    if nhom:
        if nhom not in VALID_NHOM:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"nhom phải thuộc {sorted(VALID_NHOM)}")
        stmt = stmt.where(LoaiChiPhi.nhom_default == nhom)
    return db.execute(stmt).scalars().all()


@router.post("", response_model=LoaiChiPhiOut, status_code=status.HTTP_201_CREATED)
def create_loai_chi_phi(
    body: LoaiChiPhiCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    if db.execute(select(LoaiChiPhi).where(LoaiChiPhi.ten == body.ten)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, f"Loại chi phí {body.ten!r} đã tồn tại")
    fields = body.model_dump(exclude_unset=True)
    nd = fields.get("nhom_default") or "khac"
    if nd not in VALID_NHOM:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"nhom_default phải thuộc {sorted(VALID_NHOM)}")
    fields["nhom_default"] = nd
    obj = LoaiChiPhi(**fields)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="create_loai_chi_phi", user=user, request=request,
        resource=f"loai_chi_phi:{obj.id}",
        payload={"ten": obj.ten, "nhom_default": obj.nhom_default},
    )
    return obj


@router.put("/{rid}", response_model=LoaiChiPhiOut)
def update_loai_chi_phi(
    rid: int,
    body: LoaiChiPhiUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(LoaiChiPhi, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "LoaiChiPhi không tồn tại")
    fields = body.model_dump(exclude_unset=True)
    if "ten" in fields:
        fields["ten"] = (fields["ten"] or "").strip()
        if not fields["ten"]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tên loại chi phí không được để trống")
        if fields["ten"] != obj.ten and db.execute(
            select(LoaiChiPhi.id).where(LoaiChiPhi.ten == fields["ten"], LoaiChiPhi.id != rid)
        ).first():
            raise HTTPException(status.HTTP_409_CONFLICT, f"Loại chi phí {fields['ten']!r} đã tồn tại")
    if "nhom_default" in fields and fields["nhom_default"] not in VALID_NHOM:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"nhom_default phải thuộc {sorted(VALID_NHOM)}"
        )
    for k, v in fields.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="update_loai_chi_phi", user=user, request=request,
        resource=f"loai_chi_phi:{rid}", payload=fields,
    )
    return obj


@router.delete("/{rid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_loai_chi_phi(
    rid: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(LoaiChiPhi, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "LoaiChiPhi không tồn tại")
    so_phieu = _so_phieu_dung(db, obj.ten)
    if so_phieu:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Loại {obj.ten!r} đang có {so_phieu} phiếu chi phí dùng — hãy Tạm dừng thay vì xoá.",
        )
    db.delete(obj)
    db.commit()
    log_action(
        db, app="ketoan", action="delete_loai_chi_phi", user=user, request=request,
        resource=f"loai_chi_phi:{rid}",
    )
