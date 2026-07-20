"""Router Tồn Kho — M1.

Endpoints (prefix /api/inventory):
  GET    /balance                 — list InventoryBalance rollup theo cây nhóm
  GET    /movement                — list InventoryMovement (filter product/from/to)
  POST   /movement                — manual nhập/xuất/điều chỉnh
  POST   /kiem-ke                 — chốt kiểm kê → auto sinh movement điều chỉnh
  GET    /canh-bao                — SP < ton_min hoặc > ton_max
"""
from datetime import date as _date
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import (
    CongNo, InvProduct, InvProductCategory, InventoryBalance,
    InventoryMovement, KiemKe, TaiKhoanNH, TaiKhoanNHGiaoDich,
)
from ..schemas import (
    InventoryBalanceOut, InventoryBalanceTreeNode,
    InventoryMovementCreate, InventoryMovementOut,
    KiemKeCreate, KiemKeOut, TonKhoCanhBaoOut,
)
from ..services.inventory_avg import (
    apply_movement, get_or_create_balance, InventoryError,
)
from ..services.journal import post_journal
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


# ─────────── BALANCE (rollup tree theo cây nhóm) ───────────

@router.get("/balance", response_model=list[InventoryBalanceTreeNode])
def get_balance_tree(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    q: Optional[str] = None,
):
    """Trả cây nhóm + balance per SP. Tổng SL/giá trị rollup lên cha."""
    cats = list(db.execute(
        select(InvProductCategory).order_by(
            InvProductCategory.display_order, InvProductCategory.id
        )
    ).scalars())

    products_stmt = (
        select(InvProduct, InventoryBalance)
        .outerjoin(InventoryBalance, InventoryBalance.product_id == InvProduct.id)
        .where(InvProduct.active.is_(True))
    )
    if q:
        like = f"%{q.strip()}%"
        products_stmt = products_stmt.where(
            or_(InvProduct.ma_sp.ilike(like), InvProduct.ten_sp.ilike(like))
        )

    # Build node by category
    nodes: dict[int, InventoryBalanceTreeNode] = {}
    for c in cats:
        nodes[c.id] = InventoryBalanceTreeNode(
            category_id=c.id,
            ma_nhom=c.ma_nhom,
            ten_nhom=c.ten_nhom,
        )
    # Connect parents
    roots: list[InventoryBalanceTreeNode] = []
    for c in cats:
        node = nodes[c.id]
        if c.parent_id and c.parent_id in nodes:
            nodes[c.parent_id].children.append(node)
        else:
            roots.append(node)

    cat_lookup = {c.id: c for c in cats}

    for p, b in db.execute(products_stmt):
        cid = p.category_id
        node = nodes.get(cid)
        if not node:
            continue
        sl = (b.so_luong_ton if b else 0) or Decimal("0")
        gt = (b.gia_tri_ton if b else 0) or Decimal("0")
        item = InventoryBalanceOut(
            product_id=p.id,
            so_luong_ton=sl,
            gia_von_bq=(b.gia_von_bq if b else 0) or Decimal("0"),
            gia_tri_ton=gt,
            ton_min=(b.ton_min if b else 0) or Decimal("0"),
            ton_max=(b.ton_max if b else 0) or Decimal("0"),
            last_updated=(b.last_updated if b else p.updated_at),
            ma_sp=p.ma_sp,
            ten_sp=p.ten_sp,
            dvt=p.dvt,
            category_id=cid,
            ten_nhom=cat_lookup[cid].ten_nhom if cid in cat_lookup else None,
        )
        node.products.append(item)
        node.so_sp += 1
        node.tong_sl += sl
        node.tong_gia_tri += gt

    # Rollup: cộng dồn từ leaf → root (DFS post-order)
    def _rollup(n: InventoryBalanceTreeNode) -> None:
        for ch in n.children:
            _rollup(ch)
            n.so_sp += ch.so_sp
            n.tong_sl += ch.tong_sl
            n.tong_gia_tri += ch.tong_gia_tri

    for r in roots:
        _rollup(r)
    return roots


# ─────────── MOVEMENT ───────────

@router.get("/movement", response_model=list[InventoryMovementOut])
def list_movements(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    product_id: Optional[int] = None,
    loai: Optional[str] = None,
    date_from: Annotated[Optional[_date], Query(alias="from")] = None,
    date_to: Annotated[Optional[_date], Query(alias="to")] = None,
    limit: int = Query(200, le=1000),
):
    stmt = select(InventoryMovement, InvProduct).join(
        InvProduct, InvProduct.id == InventoryMovement.product_id
    )
    if product_id:
        stmt = stmt.where(InventoryMovement.product_id == product_id)
    if loai:
        stmt = stmt.where(InventoryMovement.loai == loai)
    if date_from:
        stmt = stmt.where(InventoryMovement.ngay >= date_from)
    if date_to:
        stmt = stmt.where(InventoryMovement.ngay <= date_to)
    stmt = stmt.order_by(InventoryMovement.ngay.desc(), InventoryMovement.id.desc()).limit(limit)

    out = []
    for m, p in db.execute(stmt):
        d = InventoryMovementOut(
            id=m.id, ngay=m.ngay, product_id=m.product_id, loai=m.loai,
            so_luong=m.so_luong, don_gia=m.don_gia, thanh_tien=m.thanh_tien,
            source_app=m.source_app, source_doc_id=m.source_doc_id,
            ghi_chu=m.ghi_chu, created_by=m.created_by, created_at=m.created_at,
            ma_sp=p.ma_sp, ten_sp=p.ten_sp,
        )
        out.append(d)
    return out


@router.post(
    "/movement",
    response_model=InventoryMovementOut,
    status_code=status.HTTP_201_CREATED,
)
def create_movement(
    body: InventoryMovementCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Manual nhập/xuất/điều chỉnh. Auto recalc avg + balance."""
    p = db.get(InvProduct, body.product_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sản phẩm không tồn tại")
    if body.loai not in ("nhap", "xuat", "dieu_chinh"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "loai phải ∈ nhap | xuat | dieu_chinh",
        )

    m = InventoryMovement(
        ngay=body.ngay,
        product_id=body.product_id,
        loai=body.loai,
        so_luong=body.so_luong,
        don_gia=body.don_gia,
        thanh_tien=Decimal(body.so_luong or 0) * Decimal(body.don_gia or 0),
        source_app=body.source_app or "manual",
        source_doc_id=body.source_doc_id,
        ghi_chu=body.ghi_chu,
        created_by=user.username,
    )
    db.add(m)
    try:
        db.flush()
        apply_movement(db, m)
    except InventoryError as e:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, e.message)

    # Phase 2 — Double-entry chỉ cho loai='nhap'
    if body.loai == "nhap" and m.thanh_tien and m.thanh_tien > 0:
        thanh_tien = Decimal(str(m.thanh_tien))
        tai_khoan_id = body.tai_khoan_id
        cong_no_ncc_id = body.cong_no_ncc_id
        if tai_khoan_id:
            tk = db.get(TaiKhoanNH, tai_khoan_id)
            if not tk:
                db.rollback()
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"tai_khoan_id={tai_khoan_id} không tồn tại",
                )
            cash_acc = "111" if (tk.loai or "").strip() == "tien_mat" else "112"
            gd = TaiKhoanNHGiaoDich(
                ngay=m.ngay, tai_khoan_id=tk.id, loai="chi",
                so_tien=thanh_tien,
                ghi_chu=f"Nhập kho SP {p.ma_sp} — {m.so_luong}",
                source_app="inventory", source_doc_id=f"movement_{m.id}",
                created_by=user.username,
            )
            db.add(gd)
            db.flush()
            post_journal(
                db, ngay=m.ngay,
                mo_ta=f"Nhập kho {p.ma_sp} — TT bằng {tk.ten_tk}",
                source_type="nhap_kho_manual", source_id=str(m.id),
                by_user=user.username,
                lines=[
                    {"loai": "no", "account_code": "156",
                     "ref_table": "inventory_balance", "ref_id": p.id,
                     "so_tien": thanh_tien,
                     "ghi_chu": f"Tăng tồn kho {p.ma_sp}"},
                    {"loai": "co", "account_code": cash_acc,
                     "ref_table": "tai_khoan_nh", "ref_id": tk.id,
                     "so_tien": thanh_tien,
                     "ghi_chu": f"Chi từ {tk.ten_tk}"},
                ],
            )
        elif cong_no_ncc_id:
            cn = db.get(CongNo, cong_no_ncc_id)
            if not cn:
                db.rollback()
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"cong_no_ncc_id={cong_no_ncc_id!r} không tồn tại",
                )
            post_journal(
                db, ngay=m.ngay,
                mo_ta=f"Nhập kho {p.ma_sp} — ghi nhận phải trả NCC",
                source_type="nhap_kho_manual", source_id=str(m.id),
                by_user=user.username,
                lines=[
                    {"loai": "no", "account_code": "156",
                     "ref_table": "inventory_balance", "ref_id": p.id,
                     "so_tien": thanh_tien,
                     "ghi_chu": f"Tăng tồn kho {p.ma_sp}"},
                    {"loai": "co", "account_code": "331",
                     "ref_table": "cong_no", "ref_id": None,
                     "so_tien": thanh_tien,
                     "ghi_chu": f"Phải trả NCC ({cn.id})"},
                ],
            )

    db.commit()

    db.refresh(m)
    log_action(
        db, app="ketoan", action="create_inventory_movement",
        user=user, request=request, resource=f"inventory_movement:{m.id}",
        payload={
            "product_id": m.product_id, "loai": m.loai,
            "so_luong": str(m.so_luong), "don_gia": str(m.don_gia),
        },
    )
    return InventoryMovementOut(
        id=m.id, ngay=m.ngay, product_id=m.product_id, loai=m.loai,
        so_luong=m.so_luong, don_gia=m.don_gia, thanh_tien=m.thanh_tien,
        source_app=m.source_app, source_doc_id=m.source_doc_id,
        ghi_chu=m.ghi_chu, created_by=m.created_by, created_at=m.created_at,
        ma_sp=p.ma_sp, ten_sp=p.ten_sp,
    )


# ─────────── KIỂM KÊ ───────────

@router.post("/kiem-ke", response_model=KiemKeOut, status_code=status.HTTP_201_CREATED)
def create_kiem_ke(
    body: KiemKeCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Chốt kiểm kê 1 SP → auto sinh InventoryMovement(loai='dieu_chinh').

    chenh_lech = ton_thuc_te - ton_so_sach (sổ sách hiện tại từ balance).
    """
    p = db.get(InvProduct, body.product_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sản phẩm không tồn tại")
    bal = get_or_create_balance(db, body.product_id)
    ton_so_sach = bal.so_luong_ton or Decimal("0")
    ton_thuc_te = Decimal(body.ton_thuc_te or 0)
    chenh_lech = ton_thuc_te - ton_so_sach

    kk = KiemKe(
        ngay=body.ngay,
        product_id=body.product_id,
        ton_so_sach=ton_so_sach,
        ton_thuc_te=ton_thuc_te,
        chenh_lech=chenh_lech,
        ghi_chu=body.ghi_chu,
        created_by=user.username,
    )
    db.add(kk)
    db.flush()

    movement_id: Optional[int] = None
    if chenh_lech != 0:
        m = InventoryMovement(
            ngay=body.ngay,
            product_id=body.product_id,
            loai="dieu_chinh",
            so_luong=chenh_lech,
            don_gia=bal.gia_von_bq or Decimal("0"),
            thanh_tien=chenh_lech * (bal.gia_von_bq or Decimal("0")),
            source_app="kiem_ke",
            source_doc_id=str(kk.id),
            ghi_chu=f"Kiểm kê {body.ngay} — chênh {chenh_lech}",
            created_by=user.username,
        )
        db.add(m)
        try:
            db.flush()
            apply_movement(db, m, allow_negative=True)
            movement_id = m.id
        except InventoryError as e:
            db.rollback()
            raise HTTPException(status.HTTP_400_BAD_REQUEST, e.message)

    db.commit()
    db.refresh(kk)
    log_action(
        db, app="ketoan", action="create_kiem_ke",
        user=user, request=request, resource=f"kiem_ke:{kk.id}",
        payload={
            "product_id": kk.product_id,
            "ton_so_sach": str(kk.ton_so_sach),
            "ton_thuc_te": str(kk.ton_thuc_te),
            "chenh_lech": str(kk.chenh_lech),
            "movement_id": movement_id,
        },
    )
    return KiemKeOut(
        id=kk.id, ngay=kk.ngay, product_id=kk.product_id,
        ton_so_sach=kk.ton_so_sach, ton_thuc_te=kk.ton_thuc_te,
        chenh_lech=kk.chenh_lech, ghi_chu=kk.ghi_chu,
        created_by=kk.created_by, created_at=kk.created_at,
        movement_id=movement_id,
    )


# ─────────── CẢNH BÁO ───────────

@router.get("/canh-bao", response_model=list[TonKhoCanhBaoOut])
def list_canh_bao(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """SP có ton_min > 0 và so_luong_ton < ton_min, hoặc ton_max > 0 và > ton_max."""
    rows = db.execute(
        select(InvProduct, InventoryBalance)
        .join(InventoryBalance, InventoryBalance.product_id == InvProduct.id)
        .where(InvProduct.active.is_(True))
    ).all()
    out: list[TonKhoCanhBaoOut] = []
    for p, b in rows:
        sl = b.so_luong_ton or Decimal("0")
        tmin = b.ton_min or Decimal("0")
        tmax = b.ton_max or Decimal("0")
        if tmin > 0 and sl < tmin:
            out.append(TonKhoCanhBaoOut(
                product_id=p.id, ma_sp=p.ma_sp, ten_sp=p.ten_sp,
                so_luong_ton=sl, ton_min=tmin, ton_max=tmax,
                loai_canh_bao="duoi_min",
            ))
        elif tmax > 0 and sl > tmax:
            out.append(TonKhoCanhBaoOut(
                product_id=p.id, ma_sp=p.ma_sp, ten_sp=p.ten_sp,
                so_luong_ton=sl, ton_min=tmin, ton_max=tmax,
                loai_canh_bao="tren_max",
            ))
    return out
