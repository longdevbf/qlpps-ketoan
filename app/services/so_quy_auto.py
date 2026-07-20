"""Auto-wire SoQuy entries:
- DoanhThu created/updated → tạo SoQuy thu (lien_quan='doanh_thu', ref_id=DT-{id}).
- CongNo có khoản trả → tạo SoQuy chi (lien_quan='cong_no', ref_id=CN-{id}-pay-{seq}).
- ChiPhiPhatSinh created → tạo SoQuy chi (lien_quan='chi_phi', ref_id=CP-{id}).

Idempotent qua (lien_quan, ref_id) — gọi lại update so_tien.
Fail-soft — caller không bị block nếu sync SoQuy fail.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ChiPhiPhatSinh, CongNo, DoanhThu, SoQuy


def _upsert_so_quy(
    db: Session,
    *,
    lien_quan: str,
    ref_id: str,
    ngay,
    loai: str,            # 'thu' | 'chi'
    so_tien: Decimal,
    tai_khoan: Optional[str] = None,
    noi_dung: Optional[str] = None,
    mo_ta: Optional[str] = None,
    phan_loai_cf: Optional[str] = None,
    created_by: Optional[str] = "auto-bridge",
) -> SoQuy:
    rec = db.execute(
        select(SoQuy).where(
            SoQuy.lien_quan == lien_quan, SoQuy.ref_id == ref_id,
        )
    ).scalar_one_or_none()
    if rec is None:
        rec = SoQuy(
            lien_quan=lien_quan, ref_id=ref_id,
            created_by=created_by,
        )
        db.add(rec)
    rec.ngay = ngay
    rec.loai = loai
    rec.so_tien = so_tien
    if tai_khoan:
        rec.tai_khoan = tai_khoan
    if noi_dung:
        rec.noi_dung = noi_dung
    if mo_ta:
        rec.mo_ta = mo_ta
    if phan_loai_cf:
        rec.phan_loai_cf = phan_loai_cf
    return rec


def sync_so_quy_from_doanh_thu(db: Session, dt: DoanhThu) -> None:
    """Khi DoanhThu created/updated → tạo SoQuy thu tương ứng. Fail-soft."""
    if dt is None or dt.id is None:
        return
    try:
        _upsert_so_quy(
            db,
            lien_quan="doanh_thu",
            ref_id=f"DT-{dt.id}",
            ngay=dt.ngay,
            loai="thu",
            so_tien=Decimal(dt.so_tien or 0),
            tai_khoan=dt.ngan_hang,
            noi_dung=(dt.mo_ta or f"Thu {dt.loai_thanh_toan or 'doanh thu'} - {dt.ma_don or ''}").strip(),
            mo_ta=dt.mo_ta,
        )
        db.commit()
    except Exception:
        db.rollback()


def sync_so_quy_from_chi_phi(db: Session, cp: ChiPhiPhatSinh) -> None:
    """Khi ChiPhi created/updated → tạo SoQuy chi. Fail-soft."""
    if cp is None or cp.id is None:
        return
    try:
        _upsert_so_quy(
            db,
            lien_quan="chi_phi",
            ref_id=f"CP-{cp.id}",
            ngay=cp.ngay,
            loai="chi",
            so_tien=Decimal(cp.so_tien or 0),
            tai_khoan=cp.ngan_hang,
            noi_dung=(cp.mo_ta or f"{cp.loai_chi_phi or 'Chi phí'}").strip(),
            mo_ta=cp.mo_ta,
        )
        db.commit()
    except Exception:
        db.rollback()


def sync_so_quy_from_cong_no_payment(
    db: Session, cn: CongNo, paid_delta: Decimal,
    tai_khoan: Optional[str] = None,
    ngay_thanh_toan=None,
) -> None:
    """Khi CongNo da_tra tăng (delta) → tạo SoQuy chi cho khoản trả NCC,
    HOẶC SoQuy thu nếu là CongNo phải thu (loai='phai_thu').

    Idempotent qua ref_id = '{cn.id}-DA{seq}' (không thêm prefix CN- thừa).
    Caller pass `paid_delta` (số tiền vừa trả thêm) và `ngay_thanh_toan` (ngày thực tế trả).
    """
    if cn is None or not cn.id or paid_delta is None or paid_delta == 0:
        return
    try:
        seq = str(cn.da_tra or 0).replace(".", "_")
        sq_loai = "thu" if cn.loai == "phai_thu" else "chi"
        from datetime import date as _date_cls
        # Ưu tiên ngay_thanh_toan (do caller truyền), fallback ngay_tra, fallback today.
        # KHÔNG dùng cn.ngay (ngày phát sinh nợ) — trả tháng 5 mà nợ từ tháng 3
        # sẽ làm entry rơi sai tháng trong sổ quỹ.
        ngay_sq = (
            ngay_thanh_toan
            or getattr(cn, "ngay_tra", None)
            or _date_cls.today()
        )
        # phan_loai_cf để cashflow phân loại đúng:
        # phai_thu → thu từ KH, phai_tra → chi trả NCC/VC
        phan_loai = "thu_kh" if sq_loai == "thu" else "tra_ncc"
        _upsert_so_quy(
            db,
            lien_quan="cong_no",
            ref_id=f"{cn.id}-DA{seq}",
            ngay=ngay_sq,
            loai=sq_loai,
            so_tien=Decimal(paid_delta),
            tai_khoan=tai_khoan,
            noi_dung=f"{'Thu' if sq_loai=='thu' else 'Chi'} công nợ {cn.id} - {cn.doi_tac}",
            mo_ta=f"Trả công nợ — đối tác: {cn.doi_tac}",
            phan_loai_cf=phan_loai,
        )
        db.commit()
    except Exception as ex:
        db.rollback()
        import logging
        logging.getLogger(__name__).error(
            "sync_so_quy_from_cong_no_payment FAILED cn=%s delta=%s: %s",
            cn.id, paid_delta, ex, exc_info=True,
        )
