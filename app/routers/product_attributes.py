"""ProductAttribute API — CRUD danh mục thuộc tính theo nhóm master SP.

Sống ở app Kế Toán (master). Các app khác READ qua endpoint này.

Endpoints:
    GET    /api/product-attributes                — list (filter nhom_master/attr_key/active)
    GET    /api/product-attributes/keys           — distinct (nhom_master, attr_key) + count
    GET    /api/product-attributes/groups         — distinct nhom_master
    POST   /api/product-attributes                — create 1
    POST   /api/product-attributes/bulk           — create nhiều value cùng key
    PUT    /api/product-attributes/{aid}          — update 1
    DELETE /api/product-attributes/{aid}          — xoá 1
    DELETE /api/product-attributes/key            — xoá toàn bộ key (?nhom_master=&attr_key=)
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db
from shared.models import ProductAttribute

from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


# ─────────────────────────── Schemas ────────────────────────────────────

class AttrCreate(BaseModel):
    nhom_master: str = Field(min_length=1, max_length=64)
    # product_id NULL = áp dụng default cả nhóm; non-NULL = override per-product
    product_id: Optional[int] = None
    attr_key: str = Field(min_length=1, max_length=64)
    attr_value: str = Field(min_length=1, max_length=255)
    coeff: Optional[float] = None
    thu_tu: int = 0
    active: bool = True


class AttrBulkCreate(BaseModel):
    nhom_master: str = Field(min_length=1, max_length=64)
    product_id: Optional[int] = None
    attr_key: str = Field(min_length=1, max_length=64)
    values: list[str] = Field(min_length=1)


class AttrUpdate(BaseModel):
    attr_value: Optional[str] = Field(default=None, min_length=1, max_length=255)
    coeff: Optional[float] = None
    thu_tu: Optional[int] = None
    active: Optional[bool] = None


class AttrOut(BaseModel):
    id: int
    nhom_master: str
    product_id: Optional[int] = None
    attr_key: str
    attr_value: str
    coeff: Optional[float] = None
    thu_tu: int
    active: bool
    model_config = ConfigDict(from_attributes=True)


class CopyDefaultsBody(BaseModel):
    nhom_master: str
    product_id: int  # đích
    overwrite: bool = False  # True → xoá rows hiện có của product_id rồi copy


class KeyStat(BaseModel):
    nhom_master: str
    attr_key: str
    count: int


# ─────────────────────────── List ───────────────────────────────────────

@router.get("", response_model=list[AttrOut])
def list_attributes(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    nhom_master: Optional[str] = None,
    attr_key: Optional[str] = None,
    product_id: Optional[int] = None,
    scope: Optional[str] = None,  # "default" | "product" | "all" (default = all)
    active_only: bool = False,
):
    """List attributes.

    Filters:
    - nhom_master / attr_key / active_only — như cũ
    - product_id=X → chỉ lấy rows của SP X
    - scope="default" → chỉ rows có product_id IS NULL (mặc định nhóm)
    - scope="product" → chỉ rows có product_id IS NOT NULL
    - bỏ trống → trả cả 2 (default + per-product)
    """
    stmt = select(ProductAttribute).order_by(
        ProductAttribute.nhom_master,
        ProductAttribute.product_id.is_(None).desc(),  # default trước
        ProductAttribute.attr_key,
        ProductAttribute.thu_tu,
        ProductAttribute.id,
    )
    if nhom_master:
        stmt = stmt.where(ProductAttribute.nhom_master == nhom_master)
    if attr_key:
        stmt = stmt.where(ProductAttribute.attr_key == attr_key)
    if product_id is not None:
        stmt = stmt.where(ProductAttribute.product_id == product_id)
    elif scope == "default":
        stmt = stmt.where(ProductAttribute.product_id.is_(None))
    elif scope == "product":
        stmt = stmt.where(ProductAttribute.product_id.is_not(None))
    if active_only:
        stmt = stmt.where(ProductAttribute.active.is_(True))
    return db.execute(stmt).scalars().all()


@router.get("/keys", response_model=list[KeyStat])
def list_keys(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    nhom_master: Optional[str] = None,
):
    stmt = (
        select(
            ProductAttribute.nhom_master,
            ProductAttribute.attr_key,
            func.count(ProductAttribute.id).label("count"),
        )
        .group_by(ProductAttribute.nhom_master, ProductAttribute.attr_key)
        .order_by(ProductAttribute.nhom_master, ProductAttribute.attr_key)
    )
    if nhom_master:
        stmt = stmt.where(ProductAttribute.nhom_master == nhom_master)
    rows = db.execute(stmt).all()
    return [
        KeyStat(nhom_master=r[0], attr_key=r[1], count=r[2]) for r in rows
    ]


@router.get("/groups", response_model=list[str])
def list_groups(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Distinct nhom_master từ chính bảng attributes (đã được dùng)."""
    rows = (
        db.execute(
            select(ProductAttribute.nhom_master)
            .distinct()
            .order_by(ProductAttribute.nhom_master)
        )
        .all()
    )
    return [r[0] for r in rows if r[0]]


# ─────────────────────────── Create ─────────────────────────────────────

@router.post(
    "", response_model=AttrOut, status_code=status.HTTP_201_CREATED
)
def create_attribute(
    body: AttrCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = ProductAttribute(**body.model_dump())
    db.add(obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Đã tồn tại: {body.nhom_master} / {body.attr_key} = {body.attr_value!r}",
        )
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="create_product_attribute",
        user=user, request=request, resource=f"product_attribute:{obj.id}",
        payload=body.model_dump(),
    )
    return obj


@router.post("/bulk", response_model=list[AttrOut])
def bulk_create(
    body: AttrBulkCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Thêm nhiều value cho cùng (nhom_master, product_id, attr_key)."""
    pid_filter = (
        ProductAttribute.product_id.is_(None) if body.product_id is None
        else ProductAttribute.product_id == body.product_id
    )
    max_tt = db.execute(
        select(func.coalesce(func.max(ProductAttribute.thu_tu), 0))
        .where(
            ProductAttribute.nhom_master == body.nhom_master,
            ProductAttribute.attr_key == body.attr_key,
            pid_filter,
        )
    ).scalar_one()
    existed = set(
        db.execute(
            select(ProductAttribute.attr_value)
            .where(
                ProductAttribute.nhom_master == body.nhom_master,
                ProductAttribute.attr_key == body.attr_key,
                pid_filter,
            )
        ).scalars().all()
    )
    created = []
    for v in body.values:
        v = (v or "").strip()
        if not v or v in existed:
            continue
        max_tt += 10
        obj = ProductAttribute(
            nhom_master=body.nhom_master,
            product_id=body.product_id,
            attr_key=body.attr_key,
            attr_value=v,
            thu_tu=max_tt,
            active=True,
        )
        db.add(obj)
        created.append(obj)
        existed.add(v)
    db.commit()
    for o in created:
        db.refresh(o)
    log_action(
        db, app="ketoan", action="bulk_create_product_attribute",
        user=user, request=request,
        resource=f"product_attribute_key:{body.nhom_master}/{body.attr_key}",
        payload={"product_id": body.product_id, "added": [o.attr_value for o in created]},
    )
    return created


@router.post("/copy-defaults", response_model=dict)
def copy_defaults_to_product(
    body: CopyDefaultsBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Copy defaults nhóm → tạo per-product rows cho 1 SP cụ thể.

    Cho phép user "import" nhanh defaults rồi tinh chỉnh từng SP.
    """
    if body.overwrite:
        db.execute(
            ProductAttribute.__table__.delete().where(
                ProductAttribute.product_id == body.product_id
            )
        )
    defaults = db.execute(
        select(ProductAttribute).where(
            ProductAttribute.nhom_master == body.nhom_master,
            ProductAttribute.product_id.is_(None),
        )
    ).scalars().all()
    existing = {
        (r.attr_key, r.attr_value) for r in db.execute(
            select(ProductAttribute).where(
                ProductAttribute.product_id == body.product_id,
            )
        ).scalars().all()
    }
    created = 0
    for d in defaults:
        if (d.attr_key, d.attr_value) in existing:
            continue
        db.add(ProductAttribute(
            nhom_master=d.nhom_master,
            product_id=body.product_id,
            attr_key=d.attr_key,
            attr_value=d.attr_value,
            coeff=d.coeff,
            thu_tu=d.thu_tu,
            active=d.active,
        ))
        created += 1
    db.commit()
    log_action(
        db, app="ketoan", action="copy_attr_defaults",
        user=user, request=request,
        resource=f"product:{body.product_id}",
        payload={"nhom_master": body.nhom_master, "created": created, "overwrite": body.overwrite},
    )
    return {"ok": True, "created": created}


# ─────────────────────────── Update / Delete ───────────────────────────

@router.put("/{aid}", response_model=AttrOut)
def update_attribute(
    aid: int,
    body: AttrUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(ProductAttribute, aid)
    if not obj:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Thuộc tính không tồn tại"
        )
    fields = body.model_dump(exclude_unset=True)
    for k, v in fields.items():
        setattr(obj, k, v)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Trùng giá trị trong cùng nhóm — không thể đổi",
        )
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="update_product_attribute",
        user=user, request=request,
        resource=f"product_attribute:{aid}", payload=fields,
    )
    return obj


class KeyRename(BaseModel):
    nhom_master: str = Field(min_length=1, max_length=64)
    old_key: str = Field(min_length=1, max_length=64)
    new_key: str = Field(min_length=1, max_length=64)


@router.post("/key/rename", response_model=dict)
def rename_key(
    body: KeyRename,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Đổi tên attr_key cho toàn bộ values trong (nhom_master, old_key)."""
    if body.old_key == body.new_key:
        return {"updated": 0}
    rows = db.execute(
        select(ProductAttribute).where(
            ProductAttribute.nhom_master == body.nhom_master,
            ProductAttribute.attr_key == body.old_key,
        )
    ).scalars().all()
    if not rows:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Không tìm thấy thuộc tính {body.old_key!r} trong nhóm {body.nhom_master!r}",
        )
    # Check xung đột với new_key đã tồn tại
    existed = set(
        db.execute(
            select(ProductAttribute.attr_value).where(
                ProductAttribute.nhom_master == body.nhom_master,
                ProductAttribute.attr_key == body.new_key,
            )
        ).scalars().all()
    )
    skipped = []
    for r in rows:
        if r.attr_value in existed:
            skipped.append(r.attr_value)
            db.delete(r)  # xoá row trùng để tránh UNIQUE conflict
        else:
            r.attr_key = body.new_key
            existed.add(r.attr_value)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e.orig))
    log_action(
        db, app="ketoan", action="rename_product_attribute_key",
        user=user, request=request,
        resource=f"product_attribute_key:{body.nhom_master}/{body.old_key}",
        payload={"new_key": body.new_key, "skipped": skipped},
    )
    return {"updated": len(rows) - len(skipped), "skipped": skipped}


@router.delete("/key", status_code=status.HTTP_204_NO_CONTENT)
def delete_key(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    nhom_master: str = Query(..., min_length=1),
    attr_key: str = Query(..., min_length=1),
):
    """Xoá toàn bộ values của 1 (nhom_master, attr_key)."""
    res = db.execute(
        delete(ProductAttribute).where(
            ProductAttribute.nhom_master == nhom_master,
            ProductAttribute.attr_key == attr_key,
        )
    )
    db.commit()
    log_action(
        db, app="ketoan", action="delete_product_attribute_key",
        user=user, request=request,
        resource=f"product_attribute_key:{nhom_master}/{attr_key}",
        payload={"deleted_rows": res.rowcount},
    )


@router.delete("/{aid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attribute(
    aid: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(ProductAttribute, aid)
    if not obj:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Thuộc tính không tồn tại"
        )
    snap = {
        "nhom_master": obj.nhom_master,
        "attr_key": obj.attr_key,
        "attr_value": obj.attr_value,
    }
    db.delete(obj)
    db.commit()
    log_action(
        db, app="ketoan", action="delete_product_attribute",
        user=user, request=request,
        resource=f"product_attribute:{aid}", payload=snap,
    )
