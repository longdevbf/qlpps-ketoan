"""Service quản lý thu/chi quỹ DN — single source of truth cho `quy_dn.so_du`.

Mọi thay đổi `quy_dn.so_du` PHẢI đi qua các function ở đây để có audit trail
trong bảng `quy_dn_giao_dich` và có thể `recalc_so_du` khi nghi ngờ lệch.

Public API:
- nap_quy(...)           — thu, tăng so_du
- chi_tu_quy(...)        — chi, giảm so_du (chặn âm trừ khi allow_negative=True)
- void_giao_dich(...)    — xoá giao dịch + đảo ngược so_du
- recalc_so_du(quy_id)   — tính lại so_du = SUM(thu) - SUM(chi); self-healing

Caller PHẢI tự `db.commit()` sau khi gọi (giữ pattern cũ trong các router).
"""
from __future__ import annotations

from datetime import date as date_cls
from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..models import QuyDN, QuyDNGiaoDich


_VALID_SOURCE = {
    "manual", "trich_quy", "chi_phi", "hoan_quy", "dieu_chinh", "khac",
}


def _to_dec(v: Any) -> Decimal:
    return Decimal(str(v))


def _get_quy_or_400(db: Session, quy_id: int) -> QuyDN:
    quy = db.get(QuyDN, quy_id)
    if not quy:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Quỹ id={quy_id} không tồn tại",
        )
    if not quy.active:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Quỹ id={quy_id} đã bị deactivate",
        )
    return quy


def _normalize_source(source_type: Optional[str]) -> str:
    if not source_type:
        return "manual"
    if source_type not in _VALID_SOURCE:
        return "khac"
    return source_type


def nap_quy(
    db: Session,
    quy_id: int,
    so_tien: Any,
    ngay: date_cls,
    noi_dung: Optional[str] = None,
    source_type: str = "manual",
    source_id: Optional[str] = None,
    tai_khoan_id: Optional[int] = None,
    ghi_chu: Optional[str] = None,
    by_user: str = "",
) -> QuyDNGiaoDich:
    """Nạp tiền vào quỹ (loại='thu') + tăng `so_du`.

    Caller PHẢI tự commit sau đó.
    """
    quy = _get_quy_or_400(db, quy_id)
    amount = _to_dec(so_tien)
    if amount <= 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Số tiền nạp phải > 0",
        )

    gd = QuyDNGiaoDich(
        quy_id=quy.id,
        ngay=ngay,
        loai="thu",
        so_tien=amount,
        noi_dung=noi_dung,
        source_type=_normalize_source(source_type),
        source_id=source_id,
        tai_khoan_id=tai_khoan_id,
        ghi_chu=ghi_chu,
        created_by=by_user or None,
    )
    db.add(gd)

    quy.so_du = _to_dec(quy.so_du or 0) + amount
    db.flush()
    return gd


def chi_tu_quy(
    db: Session,
    quy_id: int,
    so_tien: Any,
    ngay: date_cls,
    noi_dung: Optional[str] = None,
    source_type: str = "manual",
    source_id: Optional[str] = None,
    tai_khoan_id: Optional[int] = None,
    ghi_chu: Optional[str] = None,
    by_user: str = "",
    allow_negative: bool = False,
) -> QuyDNGiaoDich:
    """Chi từ quỹ (loại='chi') + giảm `so_du`.

    Nếu `so_tien > so_du` và `allow_negative=False` → raise 400.

    Caller PHẢI tự commit sau đó.
    """
    quy = _get_quy_or_400(db, quy_id)
    amount = _to_dec(so_tien)
    if amount <= 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Số tiền chi phải > 0",
        )

    so_du_hien = _to_dec(quy.so_du or 0)
    if amount > so_du_hien and not allow_negative:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Số tiền chi {amount:,.0f} vượt số dư quỹ {so_du_hien:,.0f}. "
            f"Bật allow_negative=true nếu thực sự muốn cho âm.",
        )

    gd = QuyDNGiaoDich(
        quy_id=quy.id,
        ngay=ngay,
        loai="chi",
        so_tien=amount,
        noi_dung=noi_dung,
        source_type=_normalize_source(source_type),
        source_id=source_id,
        tai_khoan_id=tai_khoan_id,
        ghi_chu=ghi_chu,
        created_by=by_user or None,
    )
    db.add(gd)

    quy.so_du = so_du_hien - amount
    db.flush()
    return gd


def void_giao_dich(
    db: Session, gd_id: int, by_user: str = "",
) -> dict[str, Any]:
    """Xoá giao dịch + đảo ngược `so_du`.

    Caller PHẢI tự commit sau đó.
    """
    gd = db.get(QuyDNGiaoDich, gd_id)
    if not gd:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Giao dịch quỹ id={gd_id} không tồn tại",
        )
    quy = db.get(QuyDN, gd.quy_id)
    if not quy:
        # Quỹ đã bị xoá CASCADE — giao dịch có thể đã mất tham chiếu.
        # Vẫn xoá giao dịch để dọn data cũ.
        db.delete(gd)
        db.flush()
        return {
            "ok": True, "voided": True, "quy_id": gd.quy_id,
            "warning": "Quỹ gốc không tồn tại — không thể đảo so_du",
        }

    so_du_truoc = _to_dec(quy.so_du or 0)
    so_tien = _to_dec(gd.so_tien)
    if gd.loai == "thu":
        # Đảo: trừ so_du (vì khi nạp thì cộng)
        quy.so_du = so_du_truoc - so_tien
    else:  # 'chi'
        quy.so_du = so_du_truoc + so_tien

    payload = {
        "ok": True,
        "voided": True,
        "gd_id": gd_id,
        "quy_id": quy.id,
        "loai": gd.loai,
        "so_tien": float(so_tien),
        "so_du_truoc": float(so_du_truoc),
        "so_du_sau": float(quy.so_du),
        "by_user": by_user or "",
    }
    db.delete(gd)
    db.flush()
    return payload


def recalc_so_du(db: Session, quy_id: int) -> Decimal:
    """Tính lại `so_du` = SUM(thu) − SUM(chi). Self-healing nếu lệch.

    Returns số dư mới (Decimal). Caller PHẢI tự commit sau đó.
    """
    quy = _get_quy_or_400(db, quy_id)

    row = db.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (QuyDNGiaoDich.loai == "thu", QuyDNGiaoDich.so_tien),
                        else_=0,
                    )
                ),
                0,
            ).label("thu"),
            func.coalesce(
                func.sum(
                    case(
                        (QuyDNGiaoDich.loai == "chi", QuyDNGiaoDich.so_tien),
                        else_=0,
                    )
                ),
                0,
            ).label("chi"),
        ).where(QuyDNGiaoDich.quy_id == quy_id)
    ).one()

    new_so_du = _to_dec(row.thu or 0) - _to_dec(row.chi or 0)
    quy.so_du = new_so_du
    db.flush()
    return new_so_du
