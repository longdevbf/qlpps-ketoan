"""Router CRUD BOM Giá Vốn (M2) — mount tại /api/bom.

Endpoints:
    GET    /api/bom                        — list (filter category_id, active)
    GET    /api/bom/{id}                   — detail (kèm items)
    POST   /api/bom                        — create header + items
    PUT    /api/bom/{id}                   — update header (+ optional full-replace items)
    POST   /api/bom/{id}/clone             — tạo phiên bản mới
    DELETE /api/bom/{id}                   — soft delete (active=false)
    GET    /api/bom/margin-report          — so giá vốn BOM vs giá bán bq nhóm

Quy ước Papasan:
  - 1 BOM gắn theo category_id (nhóm SP) — nhiều SP cùng nhóm dùng chung.
  - Đổi giá NVL → POST /clone (parent.effective_to = today-1, child.effective_from = today).
  - DELETE = soft (active=false). FK ketoan.product.bom_id ON DELETE SET NULL
    cũng đảm bảo hard-delete không break SP.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import BOMMaster, BOMItem, InvProductCategory
from ..schemas import (
    BOMMasterCreate, BOMMasterUpdate, BOMMasterOut, BOMMasterListOut,
    BOMMarginReportOut,
)
from ..services.bom_calc import (
    calc_margin_by_category, next_ma_bom, recalc_bom_total,
)
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


def _enrich_out(bom: BOMMaster) -> dict:
    """Pack BOMMaster + ten_nhom (joined) thành dict cho BOMMasterOut."""
    cat = bom.category
    return {
        "id": bom.id,
        "ma_bom": bom.ma_bom,
        "ten_bom": bom.ten_bom,
        "category_id": bom.category_id,
        "ten_nhom": cat.ten_nhom if cat else None,
        "effective_from": bom.effective_from,
        "effective_to": bom.effective_to,
        "tong_gia_von": bom.tong_gia_von,
        "ghi_chu": bom.ghi_chu,
        "active": bom.active,
        "created_at": bom.created_at,
        "updated_at": bom.updated_at,
        "items": [
            {
                "id": it.id, "bom_id": it.bom_id, "ten_nvl": it.ten_nvl,
                "dvt": it.dvt, "so_luong": it.so_luong, "don_gia": it.don_gia,
                "thanh_tien": it.thanh_tien, "ghi_chu": it.ghi_chu,
                "created_at": it.created_at,
            }
            for it in (bom.items or [])
        ],
    }


# ─────────── Margin report — đăng ký TRƯỚC /{id} để khỏi bị catch-all ──

@router.get("/margin-report", response_model=list[BOMMarginReportOut])
def margin_report(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu: date = Query(..., alias="from"),
    den: date = Query(..., alias="to"),
):
    """So giá vốn BOM vs giá bán bình quân thực tế per nhóm SP trong kỳ."""
    if den < tu:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Ngày `to` phải >= `from`",
        )
    rows = calc_margin_by_category(db, tu, den)
    return rows  # type: ignore[return-value]


# ─────────── List + Detail ─────────────────────────────────────────────

@router.get("", response_model=list[BOMMasterListOut])
def list_boms(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    category_id: Optional[int] = None,
    active: Optional[bool] = None,
):
    item_count = (
        select(BOMItem.bom_id, func.count(BOMItem.id).label("c"))
        .group_by(BOMItem.bom_id)
        .subquery()
    )
    stmt = (
        select(
            BOMMaster, InvProductCategory.ten_nhom,
            func.coalesce(item_count.c.c, 0),
        )
        .join(
            InvProductCategory,
            BOMMaster.category_id == InvProductCategory.id,
            isouter=True,
        )
        .join(item_count, item_count.c.bom_id == BOMMaster.id, isouter=True)
        .order_by(BOMMaster.id.desc())
    )
    if category_id is not None:
        stmt = stmt.where(BOMMaster.category_id == category_id)
    if active is not None:
        stmt = stmt.where(BOMMaster.active.is_(active))
    rows = db.execute(stmt).all()
    out = []
    for bom, ten_nhom, n_items in rows:
        out.append({
            "id": bom.id, "ma_bom": bom.ma_bom, "ten_bom": bom.ten_bom,
            "category_id": bom.category_id, "ten_nhom": ten_nhom,
            "effective_from": bom.effective_from,
            "effective_to": bom.effective_to,
            "tong_gia_von": bom.tong_gia_von,
            "active": bom.active, "so_items": int(n_items or 0),
        })
    return out  # type: ignore[return-value]


@router.get("/{bom_id}", response_model=BOMMasterOut)
def get_bom(
    bom_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    bom = db.execute(
        select(BOMMaster)
        .options(selectinload(BOMMaster.items))
        .where(BOMMaster.id == bom_id)
    ).scalar_one_or_none()
    if not bom:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "BOM không tồn tại")
    return _enrich_out(bom)  # type: ignore[return-value]


# ─────────── Create ────────────────────────────────────────────────────

@router.post("", response_model=BOMMasterOut, status_code=status.HTTP_201_CREATED)
def create_bom(
    body: BOMMasterCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    if not db.get(InvProductCategory, body.category_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Nhóm id={body.category_id} không tồn tại",
        )
    ma_bom = (body.ma_bom or "").strip() or next_ma_bom(db)
    if db.execute(
        select(BOMMaster).where(BOMMaster.ma_bom == ma_bom)
    ).scalar_one_or_none():
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Mã BOM {ma_bom!r} đã tồn tại",
        )

    bom = BOMMaster(
        ma_bom=ma_bom,
        ten_bom=body.ten_bom,
        category_id=body.category_id,
        effective_from=body.effective_from or date.today(),
        effective_to=body.effective_to,
        ghi_chu=body.ghi_chu,
    )
    db.add(bom)
    db.flush()  # để có bom.id

    for it in body.items:
        db.add(BOMItem(
            bom_id=bom.id,
            ten_nvl=it.ten_nvl,
            dvt=it.dvt,
            so_luong=it.so_luong,
            don_gia=it.don_gia,
            ghi_chu=it.ghi_chu,
        ))
    db.flush()
    recalc_bom_total(db, bom.id)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e.orig))

    db.refresh(bom)
    log_action(
        db, app="ketoan", action="create_bom",
        user=user, request=request, resource=f"bom:{bom.id}",
        payload={"ma_bom": bom.ma_bom, "n_items": len(body.items)},
    )
    bom = db.execute(
        select(BOMMaster).options(selectinload(BOMMaster.items))
        .where(BOMMaster.id == bom.id)
    ).scalar_one()
    return _enrich_out(bom)  # type: ignore[return-value]


# ─────────── Update ────────────────────────────────────────────────────

@router.put("/{bom_id}", response_model=BOMMasterOut)
def update_bom(
    bom_id: int,
    body: BOMMasterUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    bom = db.execute(
        select(BOMMaster).options(selectinload(BOMMaster.items))
        .where(BOMMaster.id == bom_id)
    ).scalar_one_or_none()
    if not bom:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "BOM không tồn tại")

    fields = body.model_dump(exclude_unset=True, exclude={"items"})
    if "ma_bom" in fields and fields["ma_bom"] != bom.ma_bom:
        if db.execute(
            select(BOMMaster).where(
                BOMMaster.ma_bom == fields["ma_bom"],
                BOMMaster.id != bom_id,
            )
        ).scalar_one_or_none():
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Mã BOM {fields['ma_bom']!r} đã tồn tại",
            )
    if "category_id" in fields and fields["category_id"] is not None:
        if not db.get(InvProductCategory, fields["category_id"]):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Nhóm id={fields['category_id']} không tồn tại",
            )
    # Validate effective_from <= effective_to
    new_from = fields.get("effective_from", bom.effective_from)
    new_to = fields.get("effective_to", bom.effective_to)
    if new_from and new_to and new_to < new_from:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "effective_to phải >= effective_from",
        )

    for k, v in fields.items():
        setattr(bom, k, v)

    # Full-replace items nếu body.items được gửi
    if body.items is not None:
        for old in list(bom.items):
            db.delete(old)
        db.flush()
        for it in body.items:
            db.add(BOMItem(
                bom_id=bom.id,
                ten_nvl=it.ten_nvl,
                dvt=it.dvt,
                so_luong=it.so_luong,
                don_gia=it.don_gia,
                ghi_chu=it.ghi_chu,
            ))
        db.flush()
        recalc_bom_total(db, bom.id)

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e.orig))

    bom = db.execute(
        select(BOMMaster).options(selectinload(BOMMaster.items))
        .where(BOMMaster.id == bom_id)
    ).scalar_one()
    log_action(
        db, app="ketoan", action="update_bom",
        user=user, request=request, resource=f"bom:{bom_id}",
        payload=fields,
    )
    return _enrich_out(bom)  # type: ignore[return-value]


# ─────────── Clone (versioning) ────────────────────────────────────────

@router.post("/{bom_id}/clone", response_model=BOMMasterOut, status_code=status.HTTP_201_CREATED)
def clone_bom(
    bom_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Clone BOM → tạo phiên bản mới.

    - parent.effective_to = today - 1 (đóng version cũ)
    - child.effective_from = today, effective_to = NULL
    - child.ma_bom = next_ma_bom() (auto-gen mới)
    - Copy mọi item.
    """
    parent = db.execute(
        select(BOMMaster).options(selectinload(BOMMaster.items))
        .where(BOMMaster.id == bom_id)
    ).scalar_one_or_none()
    if not parent:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "BOM không tồn tại")

    today = date.today()
    yesterday = today - timedelta(days=1)
    parent.effective_to = yesterday
    parent.active = False

    child = BOMMaster(
        ma_bom=next_ma_bom(db),
        ten_bom=parent.ten_bom,
        category_id=parent.category_id,
        effective_from=today,
        effective_to=None,
        ghi_chu=(parent.ghi_chu or "") + f"\n[clone từ {parent.ma_bom}]",
        active=True,
    )
    db.add(child)
    db.flush()

    for it in parent.items:
        db.add(BOMItem(
            bom_id=child.id,
            ten_nvl=it.ten_nvl,
            dvt=it.dvt,
            so_luong=it.so_luong,
            don_gia=it.don_gia,
            ghi_chu=it.ghi_chu,
        ))
    db.flush()
    recalc_bom_total(db, child.id)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e.orig))

    log_action(
        db, app="ketoan", action="clone_bom",
        user=user, request=request, resource=f"bom:{child.id}",
        payload={"parent_id": parent.id, "parent_ma": parent.ma_bom},
    )
    bom = db.execute(
        select(BOMMaster).options(selectinload(BOMMaster.items))
        .where(BOMMaster.id == child.id)
    ).scalar_one()
    return _enrich_out(bom)  # type: ignore[return-value]


# ─────────── Soft delete ───────────────────────────────────────────────

@router.delete("/{bom_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bom(
    bom_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    bom = db.get(BOMMaster, bom_id)
    if not bom:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "BOM không tồn tại")
    bom.active = False
    db.commit()
    log_action(
        db, app="ketoan", action="delete_bom",
        user=user, request=request, resource=f"bom:{bom_id}",
        payload={"ma_bom": bom.ma_bom},
    )
