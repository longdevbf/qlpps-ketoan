"""Helper service — auto tạo entry kế toán từ 1 lệnh VC của saleadmin.

Khi 1 lệnh `saleadmin.vanchuyen` chuyển sang `trang_thai="da_giao"` hoặc
`"hoan_thanh"`:

1. Nếu `chi_phi_vc > 0` → tạo `ketoan.chi_phi_phat_sinh` row
   (loai_chi_phi="Vận chuyển", quy="Quỹ Công Ty", ref_vc=ma_vh).
2. Nếu `tien_thu_ho > 0` (COD) → tạo `ketoan.so_quy` row
   (loai="thu", lien_quan="vanchuyen", ref_vc=ma_vh).

Idempotent ở DB layer qua partial UNIQUE index `WHERE ref_vc IS NOT NULL`
(migration 0004_chi_phi_ref_vc).

Cross-app: dùng SQLAlchemy session đang sống cùng DB (qlpps_dev) — KHÔNG HTTP call.
Lazy import `saleadmin.app.models.VanChuyen` trong function body để tránh
circular import + giữ Tier 1.3 constraint (Task #3 pattern).
"""
from __future__ import annotations

from datetime import date as date_cls
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ChiPhiPhatSinh, SoQuy


# Status "trigger" kế toán — định nghĩa 1 nơi để route + service đồng bộ
VC_TRIGGER_STATUSES = {"da_giao", "hoan_thanh"}

# Loại chi phí mặc định cho chi phí vận chuyển — đảm bảo grouping P&L gom 1 chỗ
VC_LOAI_CHI_PHI = "Vận chuyển"
VC_QUY_DEFAULT = "Quỹ Công Ty"
VC_TAI_KHOAN_DEFAULT = "Tiền Mặt"


class VCAccountingError(Exception):
    """Raise khi không thể tạo entry kế toán từ VC."""

    def __init__(self, code: str, message: str):
        # 'vc_not_found' | 'not_terminal' | 'duplicate'
        self.code = code
        self.message = message
        super().__init__(message)


def _format_amount(amount: Decimal) -> str:
    """'500000.00' -> '500,000đ'. Fail-soft cho note."""
    try:
        as_int = int(Decimal(amount))
        return f"{as_int:,}đ"
    except Exception:
        return f"{amount}đ"


def _get_vc(db: Session, ma_vh: str):
    """Lazy lookup VanChuyen by ma_vh. Trả None nếu không có."""
    from saleadmin.app.models import VanChuyen  # lazy cross-app
    return db.execute(
        select(VanChuyen).where(VanChuyen.ma_vh == ma_vh)
    ).scalar_one_or_none()


def find_existing_chi_phi_for_vc(db: Session, ma_vh: str) -> Optional[ChiPhiPhatSinh]:
    """Trả ChiPhiPhatSinh nếu đã có entry chi phí VC cho ma_vh, else None."""
    return db.execute(
        select(ChiPhiPhatSinh).where(ChiPhiPhatSinh.ref_vc == ma_vh)
    ).scalar_one_or_none()


def find_existing_so_quy_for_vc(db: Session, ma_vh: str) -> Optional[SoQuy]:
    """Trả SoQuy nếu đã có entry thu COD cho ma_vh, else None."""
    return db.execute(
        select(SoQuy).where(SoQuy.ref_vc == ma_vh)
    ).scalar_one_or_none()


def create_chi_phi_from_vc(
    db: Session,
    ma_vh: str,
    *,
    created_by: Optional[str] = None,
    require_terminal: bool = True,
    commit: bool = True,
    vc=None,
) -> Optional[ChiPhiPhatSinh]:
    """Tạo ChiPhiPhatSinh từ chi_phi_vc của 1 lệnh VC. Idempotent.

    Returns:
        ChiPhiPhatSinh row nếu vừa tạo,
        None nếu chi_phi_vc <= 0 (skip — không có gì để ghi).

    Raises:
        VCAccountingError(code='vc_not_found' | 'not_terminal' | 'duplicate')
    """
    if vc is None:
        vc = _get_vc(db, ma_vh)
    if not vc:
        raise VCAccountingError("vc_not_found", f"Không tìm thấy lệnh VC {ma_vh}")

    if require_terminal and vc.trang_thai not in VC_TRIGGER_STATUSES:
        raise VCAccountingError(
            "not_terminal",
            f"Lệnh VC {ma_vh} đang ở trạng thái '{vc.trang_thai}' — chưa thể ghi "
            f"chi phí (cần status ∈ {sorted(VC_TRIGGER_STATUSES)})",
        )

    if (vc.chi_phi_vc or Decimal("0")) <= 0:
        return None  # nothing to record

    existing = find_existing_chi_phi_for_vc(db, ma_vh)
    if existing:
        raise VCAccountingError(
            "duplicate",
            f"VC {ma_vh} đã có entry chi phí (id={existing.id})",
        )

    ngay = vc.ngay_giao or (vc.updated_at.date() if vc.updated_at else None) or date_cls.today()

    mo_ta_parts = [f"Chi VC {ma_vh}"]
    if vc.ma_don:
        mo_ta_parts.append(f"đơn {vc.ma_don}")
    if vc.don_vi_vc:
        mo_ta_parts.append(f"ĐVVC {vc.don_vi_vc}")
    mo_ta_parts.append(_format_amount(vc.chi_phi_vc))
    mo_ta = " — ".join(mo_ta_parts)

    obj = ChiPhiPhatSinh(
        ngay=ngay,
        so_tien=vc.chi_phi_vc,
        loai_chi_phi=VC_LOAI_CHI_PHI,
        quy=VC_QUY_DEFAULT,
        don_vi_vc=vc.don_vi_vc,
        ma_don=vc.ma_don,
        mo_ta=mo_ta,
        ghi_chu=f"Auto-created từ VC {ma_vh}",
        ref_vc=ma_vh,
        created_by=created_by,
    )
    db.add(obj)
    if commit:
        db.commit()
        db.refresh(obj)
    else:
        db.flush()
    return obj


def create_thu_cod_from_vc(
    db: Session,
    ma_vh: str,
    *,
    created_by: Optional[str] = None,
    require_terminal: bool = True,
    commit: bool = True,
    vc=None,
) -> Optional[SoQuy]:
    """Tạo SoQuy(loai='thu') từ tien_thu_ho (COD) của 1 lệnh VC. Idempotent.

    Returns:
        SoQuy row nếu vừa tạo,
        None nếu tien_thu_ho <= 0 (skip — không có COD).

    Raises:
        VCAccountingError(code='vc_not_found' | 'not_terminal' | 'duplicate')
    """
    if vc is None:
        vc = _get_vc(db, ma_vh)
    if not vc:
        raise VCAccountingError("vc_not_found", f"Không tìm thấy lệnh VC {ma_vh}")

    if require_terminal and vc.trang_thai not in VC_TRIGGER_STATUSES:
        raise VCAccountingError(
            "not_terminal",
            f"Lệnh VC {ma_vh} đang ở trạng thái '{vc.trang_thai}' — chưa thể ghi "
            f"thu COD (cần status ∈ {sorted(VC_TRIGGER_STATUSES)})",
        )

    if (vc.tien_thu_ho or Decimal("0")) <= 0:
        return None

    existing = find_existing_so_quy_for_vc(db, ma_vh)
    if existing:
        raise VCAccountingError(
            "duplicate",
            f"VC {ma_vh} đã có entry thu sổ quỹ (id={existing.id})",
        )

    ngay = vc.ngay_giao or (vc.updated_at.date() if vc.updated_at else None) or date_cls.today()

    noi_dung_parts = [f"Thu hộ COD VC {ma_vh}"]
    if vc.ma_don:
        noi_dung_parts.append(f"đơn {vc.ma_don}")
    if vc.ten_kh:
        noi_dung_parts.append(f"KH {vc.ten_kh}")
    noi_dung_parts.append(_format_amount(vc.tien_thu_ho))
    noi_dung = " — ".join(noi_dung_parts)

    obj = SoQuy(
        ngay=ngay,
        loai="thu",
        so_tien=vc.tien_thu_ho,
        tai_khoan=VC_TAI_KHOAN_DEFAULT,
        noi_dung=noi_dung,
        lien_quan="vanchuyen",
        ref_id=vc.ma_don,
        ref_vc=ma_vh,
        phan_loai_cf="thu_kh",
        ghi_chu=f"Auto-created từ VC {ma_vh}",
        created_by=created_by,
    )
    db.add(obj)
    if commit:
        db.commit()
        db.refresh(obj)
    else:
        db.flush()
    return obj


def create_all_from_vc(
    db: Session,
    ma_vh: str,
    *,
    created_by: Optional[str] = None,
    require_terminal: bool = True,
    commit: bool = True,
) -> dict:
    """Gọi cả 2: chi phí VC + thu COD. 1 transaction (commit cuối).

    Returns:
        {
            'ma_vh': str,
            'chi_phi': ChiPhiPhatSinh | None,
            'so_quy':  SoQuy | None,
            'created': ['chi_phi'?, 'so_quy'?],
            'skipped': ['chi_phi'?, 'so_quy'?],   # khi amount = 0
        }

    Raises:
        VCAccountingError — propagate (vc_not_found / not_terminal / duplicate).
        Nếu 1 trong 2 đã có entry → raise duplicate ngay (không tạo phần còn lại).
    """
    vc = _get_vc(db, ma_vh)
    if not vc:
        raise VCAccountingError("vc_not_found", f"Không tìm thấy lệnh VC {ma_vh}")

    if require_terminal and vc.trang_thai not in VC_TRIGGER_STATUSES:
        raise VCAccountingError(
            "not_terminal",
            f"Lệnh VC {ma_vh} đang ở trạng thái '{vc.trang_thai}' — chưa thể ghi "
            f"kế toán (cần status ∈ {sorted(VC_TRIGGER_STATUSES)})",
        )

    chi_phi = None
    so_quy = None
    created: list[str] = []
    skipped: list[str] = []

    # Chi phí VC
    if (vc.chi_phi_vc or Decimal("0")) > 0:
        chi_phi = create_chi_phi_from_vc(
            db, ma_vh, created_by=created_by,
            require_terminal=False, commit=False, vc=vc,
        )
        if chi_phi:
            created.append("chi_phi")
    else:
        skipped.append("chi_phi")

    # Thu COD
    if (vc.tien_thu_ho or Decimal("0")) > 0:
        so_quy = create_thu_cod_from_vc(
            db, ma_vh, created_by=created_by,
            require_terminal=False, commit=False, vc=vc,
        )
        if so_quy:
            created.append("so_quy")
    else:
        skipped.append("so_quy")

    if commit:
        db.commit()
        if chi_phi:
            db.refresh(chi_phi)
        if so_quy:
            db.refresh(so_quy)

    return {
        "ma_vh": ma_vh,
        "chi_phi": chi_phi,
        "so_quy": so_quy,
        "created": created,
        "skipped": skipped,
    }
