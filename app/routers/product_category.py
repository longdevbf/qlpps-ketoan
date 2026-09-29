"""Router cây danh mục sản phẩm — M1 inventory.

Endpoints (prefix /api/product-category):
  GET    /tree           — cây phân cấp + product_count
  GET    /                — flat list
  POST   /                — create
  PUT    /{id}            — update
  DELETE /{id}            — chặn nếu còn SP con / nhóm con
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import InvProductCategory, InvProduct
from ..schemas import (
    InvProductCategoryCreate, InvProductCategoryUpdate,
    InvProductCategoryOut, InvProductCategoryNode,
)
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


@router.get("/tree", response_model=list[InvProductCategoryNode])
def get_tree(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    active_only: bool = True,
):
    """Trả cây phân cấp + product_count per node (count SP active)."""
    stmt = select(InvProductCategory).order_by(
        InvProductCategory.display_order, InvProductCategory.id
    )
    if active_only:
        stmt = stmt.where(InvProductCategory.active.is_(True))
    rows = list(db.execute(stmt).scalars())

    # Count SP per category
    pcounts = {
        cid: cnt for cid, cnt in db.execute(
            select(InvProduct.category_id, func.count(InvProduct.id))
            .where(InvProduct.active.is_(True))
            .group_by(InvProduct.category_id)
        ).all()
    }

    # Build tree
    by_id: dict[int, InvProductCategoryNode] = {}
    for r in rows:
        node = InvProductCategoryNode.model_validate(r)
        # model_validate đã nạp sẵn quan hệ ORM `children` (nút con thiếu product_count) —
        # xoá đi để chỉ dựng cây một lần bên dưới, tránh nhóm con hiện 2 lần.
        node.children = []
        node.product_count = int(pcounts.get(r.id, 0))
        by_id[r.id] = node

    roots: list[InvProductCategoryNode] = []
    for r in rows:
        node = by_id[r.id]
        if r.parent_id and r.parent_id in by_id:
            by_id[r.parent_id].children.append(node)
        else:
            roots.append(node)
    return roots


@router.get("", response_model=list[InvProductCategoryOut])
def list_categories(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    active_only: bool = True,
):
    stmt = select(InvProductCategory).order_by(
        InvProductCategory.display_order, InvProductCategory.id
    )
    if active_only:
        stmt = stmt.where(InvProductCategory.active.is_(True))
    return list(db.execute(stmt).scalars())


@router.post(
    "",
    response_model=InvProductCategoryOut,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    body: InvProductCategoryCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    if db.execute(
        select(InvProductCategory).where(InvProductCategory.ma_nhom == body.ma_nhom)
    ).scalar_one_or_none():
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Mã nhóm {body.ma_nhom!r} đã tồn tại"
        )
    if body.parent_id and not db.get(InvProductCategory, body.parent_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Nhóm cha id={body.parent_id} không tồn tại"
        )
    obj = InvProductCategory(**body.model_dump())
    db.add(obj)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e.orig))
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="create_product_category",
        user=user, request=request, resource=f"product_category:{obj.id}",
        payload={"ma_nhom": obj.ma_nhom, "ten_nhom": obj.ten_nhom},
    )
    return obj


@router.put("/{cid}", response_model=InvProductCategoryOut)
def update_category(
    cid: int,
    body: InvProductCategoryUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(InvProductCategory, cid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nhóm không tồn tại")
    fields = body.model_dump(exclude_unset=True)
    if fields.get("parent_id") == cid:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "parent_id không được trỏ về chính nó"
        )
    if "ma_nhom" in fields and fields["ma_nhom"] != obj.ma_nhom:
        if db.execute(
            select(InvProductCategory).where(
                InvProductCategory.ma_nhom == fields["ma_nhom"],
                InvProductCategory.id != cid,
            )
        ).scalar_one_or_none():
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Mã nhóm {fields['ma_nhom']!r} đã tồn tại"
            )
    for k, v in fields.items():
        setattr(obj, k, v)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e.orig))
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="update_product_category",
        user=user, request=request, resource=f"product_category:{cid}",
        payload=fields,
    )
    return obj


@router.delete("/{cid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    cid: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(InvProductCategory, cid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nhóm không tồn tại")

    n_children = db.execute(
        select(func.count(InvProductCategory.id)).where(
            InvProductCategory.parent_id == cid
        )
    ).scalar() or 0
    if n_children:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Còn {n_children} nhóm con — di chuyển/xoá nhóm con trước",
        )
    n_prod = db.execute(
        select(func.count(InvProduct.id)).where(InvProduct.category_id == cid)
    ).scalar() or 0
    if n_prod:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Còn {n_prod} sản phẩm thuộc nhóm — di chuyển SP trước",
        )
    db.delete(obj)
    db.commit()
    log_action(
        db, app="ketoan", action="delete_product_category",
        user=user, request=request, resource=f"product_category:{cid}",
        payload={"ma_nhom": obj.ma_nhom},
    )
