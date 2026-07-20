"""Router CRUD InvProduct — M1 inventory products (KHÁC shared catalog).

Mount tại /api/product (singular). Shared catalog dùng /api/products (plural).
"""
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import InvProduct, InvProductCategory, InventoryBalance, InventoryMovement
from ..schemas import (
    InvProductCreate, InvProductUpdate, InvProductOut, InvProductPage,
)
from ._deps import require_ketoan_user


def _enrich_with_balance(
    db: Session, prods: list[InvProduct]
) -> list[InvProductOut]:
    """Issue 4 — LEFT JOIN inventory_balance để FE hiển thị tồn + giá vốn BQ."""
    if not prods:
        return []
    pids = [p.id for p in prods]
    rows = db.execute(
        select(
            InventoryBalance.product_id,
            InventoryBalance.so_luong_ton,
            InventoryBalance.gia_von_bq,
        ).where(InventoryBalance.product_id.in_(pids))
    ).all()
    bal_map = {pid: (sl, gv) for pid, sl, gv in rows}
    out: list[InvProductOut] = []
    for p in prods:
        sl, gv = bal_map.get(p.id, (Decimal("0"), Decimal("0")))
        item = InvProductOut.model_validate(p)
        item.so_luong_ton = sl or Decimal("0")
        item.gia_von_bq = gv or Decimal("0")
        out.append(item)
    return out


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


@router.get("", response_model=InvProductPage)
def list_products(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    category_id: Optional[int] = None,
    q: Optional[str] = None,
    active_only: bool = True,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
):
    stmt = select(InvProduct)
    cnt_stmt = select(func.count(InvProduct.id))
    if active_only:
        stmt = stmt.where(InvProduct.active.is_(True))
        cnt_stmt = cnt_stmt.where(InvProduct.active.is_(True))
    if category_id:
        stmt = stmt.where(InvProduct.category_id == category_id)
        cnt_stmt = cnt_stmt.where(InvProduct.category_id == category_id)
    if q:
        like = f"%{q.strip()}%"
        cond = or_(InvProduct.ma_sp.ilike(like), InvProduct.ten_sp.ilike(like))
        stmt = stmt.where(cond)
        cnt_stmt = cnt_stmt.where(cond)

    total = int(db.execute(cnt_stmt).scalar() or 0)
    stmt = stmt.order_by(InvProduct.ma_sp).limit(size).offset((page - 1) * size)
    items = list(db.execute(stmt).scalars())
    enriched = _enrich_with_balance(db, items)
    return InvProductPage(total=total, page=page, size=size, items=enriched)


@router.get("/{pid}", response_model=InvProductOut)
def get_product(
    pid: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    p = db.get(InvProduct, pid)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sản phẩm không tồn tại")
    enriched = _enrich_with_balance(db, [p])
    return enriched[0]


@router.put("/by-ma-sp/{ma_sp}/category")
def set_category_by_ma_sp(
    ma_sp: str,
    body: dict,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Upsert `ketoan.product` cho 1 SP theo `ma_sp` — chỉ set `category_id`.

    Idempotent — gọi từ form Sản Phẩm (Kế Toán) khi user chọn dropdown "Danh Mục".
    Tạo mới nếu `ma_sp` chưa có trong `ketoan.product` (yêu cầu ten_sp).

    Body: {"category_id": int, "ten_sp": str (chỉ dùng khi tạo mới),
           "dvt": str optional}
    """
    cat_id = body.get("category_id")
    if cat_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Thiếu category_id")
    if not db.get(InvProductCategory, cat_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Nhóm id={cat_id} không tồn tại"
        )

    existing = db.execute(
        select(InvProduct).where(InvProduct.ma_sp == ma_sp)
    ).scalar_one_or_none()

    if existing:
        existing.category_id = cat_id
        action = "updated"
    else:
        ten = (body.get("ten_sp") or ma_sp).strip()
        existing = InvProduct(
            ma_sp=ma_sp,
            ten_sp=ten,
            category_id=cat_id,
            dvt=body.get("dvt"),
            active=True,
        )
        db.add(existing)
        action = "created"
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e.orig))
    db.refresh(existing)
    log_action(
        db, app="ketoan", action=f"{action}_inv_product_category",
        user=user, request=request, resource=f"inv_product:{existing.id}",
        payload={"ma_sp": ma_sp, "category_id": cat_id},
    )
    return {"ok": True, "action": action, "id": existing.id, "category_id": cat_id}


@router.post("", response_model=InvProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    body: InvProductCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    if db.execute(
        select(InvProduct).where(InvProduct.ma_sp == body.ma_sp)
    ).scalar_one_or_none():
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Mã SP {body.ma_sp!r} đã tồn tại"
        )
    if not db.get(InvProductCategory, body.category_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Nhóm id={body.category_id} không tồn tại"
        )
    obj = InvProduct(**body.model_dump())
    db.add(obj)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e.orig))
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="create_inv_product",
        user=user, request=request, resource=f"inv_product:{obj.id}",
        payload={"ma_sp": obj.ma_sp, "ten_sp": obj.ten_sp},
    )
    return _enrich_with_balance(db, [obj])[0]


@router.put("/{pid}", response_model=InvProductOut)
def update_product(
    pid: int,
    body: InvProductUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(InvProduct, pid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sản phẩm không tồn tại")
    fields = body.model_dump(exclude_unset=True)
    if "ma_sp" in fields and fields["ma_sp"] != obj.ma_sp:
        if db.execute(
            select(InvProduct).where(
                InvProduct.ma_sp == fields["ma_sp"],
                InvProduct.id != pid,
            )
        ).scalar_one_or_none():
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Mã SP {fields['ma_sp']!r} đã tồn tại"
            )
    if "category_id" in fields and not db.get(
        InvProductCategory, fields["category_id"]
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Nhóm id={fields['category_id']} không tồn tại"
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
        db, app="ketoan", action="update_inv_product",
        user=user, request=request, resource=f"inv_product:{pid}",
        payload=fields,
    )
    return _enrich_with_balance(db, [obj])[0]


@router.delete("/{pid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    pid: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(InvProduct, pid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sản phẩm không tồn tại")
    n_mv = db.execute(
        select(func.count(InventoryMovement.id)).where(
            InventoryMovement.product_id == pid
        )
    ).scalar() or 0
    if n_mv:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Sản phẩm có {n_mv} biến động kho — không thể xoá. "
            f"Set active=false thay vì xoá.",
        )
    ma_sp = obj.ma_sp
    db.delete(obj)
    db.commit()
    log_action(
        db, app="ketoan", action="delete_inv_product",
        user=user, request=request, resource=f"inv_product:{pid}",
        payload={"ma_sp": ma_sp},
    )
