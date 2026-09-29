"""Product master catalog — CRUD (Kế Toán quản lý).

Các app khác (baogia/marketing/saleadmin/muahang) chỉ READ qua router riêng
của họ. Đây là endpoint duy nhất có quyền thêm/sửa/xoá.

Endpoints:
    GET    /api/products                        — list (filter active/nhom_hang/q)
    GET    /api/products/{id}                   — detail by id
    GET    /api/products/by-ma-sp/{ma_sp}       — detail by ma_sp
    POST   /api/products                        — create + addons
    PUT    /api/products/{id}                   — update fields cơ bản
    DELETE /api/products/{id}                   — xoá hẳn (CASCADE addons)
    POST   /api/products/{id}/addons            — add addon
    PUT    /api/products/{id}/addons/{aid}      — update addon
    DELETE /api/products/{id}/addons/{aid}      — xoá addon
    GET    /api/products/meta/nhom-hang         — list nhóm hàng distinct
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db
from shared.models import Product, ProductAddon

from ..schemas import (
    ProductAddonCreate, ProductAddonOut, ProductAddonUpdate,
    ProductCreate, ProductOut, ProductUpdate,
)
from ..services.tim_kiem import khop_mot_trong
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


# ─────────────────────────── List / Detail ──────────────────────────────

@router.get("", response_model=list[ProductOut])
def list_products(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    active_only: bool = True,
    nhom_hang: Optional[str] = None,
    nhom_master: Optional[str] = None,
    q: Optional[str] = None,
):
    stmt = (
        select(Product)
        .options(selectinload(Product.addons))
        .order_by(Product.thu_tu, Product.id)
    )
    if active_only:
        stmt = stmt.where(Product.active.is_(True))
    if nhom_hang:
        stmt = stmt.where(Product.nhom_hang == nhom_hang)
    if nhom_master:
        stmt = stmt.where(Product.nhom_master == nhom_master)
    if q and q.strip():
        # Không phân biệt dấu + hoa/thường — services/tim_kiem.py.
        stmt = stmt.where(khop_mot_trong((Product.ten_sp, Product.ma_sp), q))
    return db.execute(stmt).scalars().all()


@router.get("/meta/nhom-hang", response_model=list[str])
def list_nhom_hang(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    stmt = (
        select(Product.nhom_hang)
        .where(Product.nhom_hang.is_not(None))
        .distinct()
        .order_by(Product.nhom_hang)
    )
    return [row[0] for row in db.execute(stmt).all() if row[0]]


@router.get("/{pid}", response_model=ProductOut)
def get_product(
    pid: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    stmt = (
        select(Product)
        .options(selectinload(Product.addons))
        .where(Product.id == pid)
    )
    p = db.execute(stmt).scalar_one_or_none()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sản phẩm không tồn tại")
    return p


@router.get("/by-ma-sp/{ma_sp}", response_model=ProductOut)
def get_product_by_ma_sp(
    ma_sp: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    stmt = (
        select(Product)
        .options(selectinload(Product.addons))
        .where(Product.ma_sp == ma_sp)
    )
    p = db.execute(stmt).scalar_one_or_none()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Không tìm thấy SP: {ma_sp}")
    return p


# ─────────────────────────── CRUD Product ───────────────────────────────

@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    body: ProductCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    if db.execute(select(Product).where(Product.ma_sp == body.ma_sp)).scalar_one_or_none():
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Mã SP {body.ma_sp!r} đã tồn tại"
        )

    addons_data = body.addons
    fields = body.model_dump(exclude={"addons"}, exclude_unset=True)
    obj = Product(**fields)
    for a in addons_data:
        obj.addons.append(ProductAddon(**a.model_dump(exclude_unset=True)))
    db.add(obj)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e.orig))
    db.refresh(obj)

    log_action(
        db, app="ketoan", action="create_product", user=user, request=request,
        resource=f"product:{obj.id}",
        payload={"ma_sp": obj.ma_sp, "ten_sp": obj.ten_sp, "addons": len(obj.addons)},
    )
    return obj


@router.put("/{pid}", response_model=ProductOut)
def update_product(
    pid: int,
    body: ProductUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(Product, pid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sản phẩm không tồn tại")

    fields = body.model_dump(exclude_unset=True)
    if "ma_sp" in fields and fields["ma_sp"] != obj.ma_sp:
        if db.execute(
            select(Product).where(Product.ma_sp == fields["ma_sp"], Product.id != pid)
        ).scalar_one_or_none():
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Mã SP {fields['ma_sp']!r} đã tồn tại"
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
        db, app="ketoan", action="update_product", user=user, request=request,
        resource=f"product:{pid}", payload=fields,
    )
    return obj


@router.delete("/{pid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    pid: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    from shared.utils.uploads import delete_file

    obj = db.get(Product, pid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sản phẩm không tồn tại")
    ma_sp, ten_sp, hinh_anh = obj.ma_sp, obj.ten_sp, obj.hinh_anh
    db.delete(obj)
    db.commit()

    # Xoá file ảnh vật lý nếu có
    if hinh_anh and hinh_anh.startswith("/api/files/products/"):
        parts = hinh_anh.split("/")
        if len(parts) >= 6:
            delete_file("ketoan", f"product_{pid}", parts[5])

    log_action(
        db, app="ketoan", action="delete_product", user=user, request=request,
        resource=f"product:{pid}", payload={"ma_sp": ma_sp, "ten_sp": ten_sp},
    )


# ─────────────────────────── CRUD Addon ─────────────────────────────────

@router.post(
    "/{pid}/addons",
    response_model=ProductAddonOut,
    status_code=status.HTTP_201_CREATED,
)
def create_addon(
    pid: int,
    body: ProductAddonCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    if not db.get(Product, pid):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sản phẩm không tồn tại")
    addon = ProductAddon(product_id=pid, **body.model_dump(exclude_unset=True))
    db.add(addon)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e.orig))
    db.refresh(addon)
    log_action(
        db, app="ketoan", action="create_product_addon", user=user, request=request,
        resource=f"product_addon:{addon.id}",
        payload={"product_id": pid, "ten_addon": addon.ten_addon},
    )
    return addon


@router.put("/{pid}/addons/{aid}", response_model=ProductAddonOut)
def update_addon(
    pid: int,
    aid: int,
    body: ProductAddonUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    addon = db.get(ProductAddon, aid)
    if not addon or addon.product_id != pid:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Addon không tồn tại")
    fields = body.model_dump(exclude_unset=True)
    for k, v in fields.items():
        setattr(addon, k, v)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e.orig))
    db.refresh(addon)
    log_action(
        db, app="ketoan", action="update_product_addon", user=user, request=request,
        resource=f"product_addon:{aid}", payload=fields,
    )
    return addon


@router.delete("/{pid}/addons/{aid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_addon(
    pid: int,
    aid: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    addon = db.get(ProductAddon, aid)
    if not addon or addon.product_id != pid:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Addon không tồn tại")
    db.delete(addon)
    db.commit()
    log_action(
        db, app="ketoan", action="delete_product_addon", user=user, request=request,
        resource=f"product_addon:{aid}",
    )
