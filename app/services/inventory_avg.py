"""Logic giá vốn bình quân gia quyền (M1).

Cập nhật InventoryBalance từ 1 InventoryMovement, áp dụng đúng quy ước Papasan:
  - nhap : recalc avg = (sl_cu*avg_cu + sl_nhap*don_gia) / (sl_cu + sl_nhap)
  - xuat : don_gia OUT = current avg (auto override input), thanh_tien = sl * avg
  - dieu_chinh: giá vốn không đổi, chỉ chỉnh số lượng (so_luong có thể âm)

Không tạo balance row mới ở đây — caller chịu trách nhiệm `db.add(balance)`
nếu chưa có. Service operate trên SA Session, gọi `db.flush()` để ID/version
sẵn sàng cho FK / response model nhưng KHÔNG commit.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..models import InventoryBalance, InventoryMovement, InvProduct


_ZERO = Decimal("0")


class InventoryError(Exception):
    """Raise khi không thể apply movement (vd: âm tồn)."""

    def __init__(self, code: str, message: str):
        self.code = code  # 'invalid_loai' | 'product_not_found' | 'negative_qty'
        self.message = message
        super().__init__(message)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def get_or_create_balance(db: Session, product_id: int) -> InventoryBalance:
    """Return existing balance row, hoặc tạo mới (chưa commit)."""
    bal = db.get(InventoryBalance, product_id)
    if bal:
        return bal
    if not db.get(InvProduct, product_id):
        raise InventoryError("product_not_found", f"Sản phẩm id={product_id} không tồn tại")
    bal = InventoryBalance(
        product_id=product_id,
        so_luong_ton=_ZERO,
        gia_von_bq=_ZERO,
        gia_tri_ton=_ZERO,
        ton_min=_ZERO,
        ton_max=_ZERO,
    )
    db.add(bal)
    db.flush()
    return bal


def apply_movement(
    db: Session,
    movement: InventoryMovement,
    *,
    allow_negative: bool = False,
) -> InventoryBalance:
    """Cập nhật InventoryBalance từ 1 movement (chưa commit).

    - nhap : recalc avg
    - xuat : don_gia OUT = current avg (override movement.don_gia + thanh_tien)
    - dieu_chinh: giá vốn KHÔNG đổi (so_luong có thể âm)

    Args:
        allow_negative: True nếu cho phép balance âm (vd: kiểm kê truy hồi).
            Mặc định False — raise nếu xuất quá tồn.

    Raises:
        InventoryError(code=invalid_loai | negative_qty | product_not_found)
    """
    if movement.loai not in ("nhap", "xuat", "dieu_chinh"):
        raise InventoryError("invalid_loai", f"loai phải ∈ nhap|xuat|dieu_chinh, got {movement.loai!r}")

    bal = get_or_create_balance(db, movement.product_id)

    sl = Decimal(movement.so_luong or 0)
    dg = Decimal(movement.don_gia or 0)

    if movement.loai == "nhap":
        if sl <= 0:
            raise InventoryError("negative_qty", "Nhập kho yêu cầu so_luong > 0")
        new_qty = (bal.so_luong_ton or _ZERO) + sl
        if new_qty > 0:
            new_avg = (
                (bal.so_luong_ton or _ZERO) * (bal.gia_von_bq or _ZERO)
                + sl * dg
            ) / new_qty
        else:
            new_avg = _ZERO
        bal.so_luong_ton = new_qty
        bal.gia_von_bq = new_avg
        movement.thanh_tien = sl * dg

    elif movement.loai == "xuat":
        if sl <= 0:
            raise InventoryError("negative_qty", "Xuất kho yêu cầu so_luong > 0")
        if not allow_negative and (bal.so_luong_ton or _ZERO) < sl:
            raise InventoryError(
                "negative_qty",
                f"Tồn kho không đủ — cần {sl}, hiện có {bal.so_luong_ton or 0}",
            )
        # Giá vốn xuất = avg hiện tại
        avg = bal.gia_von_bq or _ZERO
        movement.don_gia = avg
        movement.thanh_tien = sl * avg
        bal.so_luong_ton = (bal.so_luong_ton or _ZERO) - sl
        # avg không đổi

    elif movement.loai == "dieu_chinh":
        # so_luong có thể âm. Giá vốn không đổi.
        new_qty = (bal.so_luong_ton or _ZERO) + sl
        if not allow_negative and new_qty < 0:
            raise InventoryError(
                "negative_qty",
                f"Điều chỉnh làm tồn âm — sau adjust: {new_qty}",
            )
        bal.so_luong_ton = new_qty
        avg = bal.gia_von_bq or _ZERO
        movement.don_gia = avg
        movement.thanh_tien = sl * avg

    bal.gia_tri_ton = (bal.so_luong_ton or _ZERO) * (bal.gia_von_bq or _ZERO)
    bal.last_updated = _now()
    db.flush()
    return bal


def recalc_balance_from_history(
    db: Session,
    product_id: int,
) -> Optional[InventoryBalance]:
    """Tính lại InventoryBalance bằng cách replay toàn bộ InventoryMovement.

    Dùng cho data backfill / repair. Order chronological theo ngay rồi id.
    """
    from sqlalchemy import select

    bal = get_or_create_balance(db, product_id)
    bal.so_luong_ton = _ZERO
    bal.gia_von_bq = _ZERO
    bal.gia_tri_ton = _ZERO

    rows = list(db.execute(
        select(InventoryMovement)
        .where(InventoryMovement.product_id == product_id)
        .order_by(InventoryMovement.ngay, InventoryMovement.id)
    ).scalars())
    for m in rows:
        sl = Decimal(m.so_luong or 0)
        dg = Decimal(m.don_gia or 0)
        if m.loai == "nhap":
            new_qty = bal.so_luong_ton + sl
            if new_qty > 0:
                bal.gia_von_bq = (
                    bal.so_luong_ton * bal.gia_von_bq + sl * dg
                ) / new_qty
            else:
                bal.gia_von_bq = _ZERO
            bal.so_luong_ton = new_qty
        elif m.loai == "xuat":
            bal.so_luong_ton -= sl
        elif m.loai == "dieu_chinh":
            bal.so_luong_ton += sl
    bal.gia_tri_ton = bal.so_luong_ton * bal.gia_von_bq
    bal.last_updated = _now()
    db.flush()
    return bal
