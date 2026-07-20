"""Auto-bridge marketing.ads_cost → ketoan.chi_phi_phat_sinh.

Quy ước:
- 1 row ChiPhi / (tháng × kênh) — gộp tất cả entries daily.
- ngay = thang-01 (ngày đầu tháng).
- ref_ads_thang_kenh = 'ADS-{thang}-{kenh_slug}' để idempotent.
- loai_chi_phi = 'Quảng cáo - {kenh}' (lookup hoặc auto-create LoaiChiPhi).
- phong_ban = 'Marketing'.

Gọi `sync_chi_phi_from_ads(db, thang)` để đồng bộ 1 tháng. Idempotent — gọi
lại sẽ UPDATE so_tien (nếu marketing edit ads_cost), KHÔNG nhân đôi.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ChiPhiPhatSinh, LoaiChiPhi


def _slug(s: str) -> str:
    out = []
    for ch in (s or "").lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("_")
    return "".join(out).strip("_")[:32] or "khac"


def _ensure_loai_chi_phi(db: Session, ten: str, mo_ta: str = "") -> str:
    """Đảm bảo có LoaiChiPhi `ten`. Trả về `ten` để lưu vào ChiPhi.loai_chi_phi."""
    existing = db.execute(
        select(LoaiChiPhi).where(LoaiChiPhi.ten == ten)
    ).scalar_one_or_none()
    if existing:
        return existing.ten
    rec = LoaiChiPhi(ten=ten, mo_ta=mo_ta or None)
    db.add(rec)
    db.flush()
    return rec.ten


def sync_chi_phi_from_ads(
    db: Session, thang: str, *, nguoi_chi: Optional[str] = "auto-bridge",
) -> dict:
    """Đồng bộ chi phí ADS marketing → ketoan.chi_phi cho tháng `thang` ('YYYY-MM').

    Trả `{ok, thang, upserted, total_amount, by_kenh: {...}}`.
    """
    try:
        from marketing.app.models import AdsCost  # noqa: WPS433
    except ImportError:
        return {"ok": False, "error": "marketing.AdsCost not available"}

    yr, mo = map(int, thang.split("-"))
    ngay_dau = date(yr, mo, 1)

    rows = db.execute(
        select(
            AdsCost.kenh,
            func.coalesce(func.sum(AdsCost.chi_phi), 0).label("total"),
        )
        .where(AdsCost.thang == thang)
        .group_by(AdsCost.kenh)
    ).all()

    upserted = 0
    by_kenh: dict[str, float] = {}
    total_amount = Decimal(0)

    for kenh, total in rows:
        if not kenh or not total:
            continue
        kenh_label = str(kenh).strip()
        ref = f"ADS-{thang}-{_slug(kenh_label)}"
        loai_ten = _ensure_loai_chi_phi(
            db, f"Quảng cáo - {kenh_label}",
            mo_ta="Auto-tạo từ marketing.ads_cost",
        )

        rec = db.execute(
            select(ChiPhiPhatSinh).where(ChiPhiPhatSinh.ref_ads_thang_kenh == ref)
        ).scalar_one_or_none()
        if rec is None:
            rec = ChiPhiPhatSinh(
                ngay=ngay_dau,
                ref_ads_thang_kenh=ref,
                created_by=nguoi_chi,
            )
            db.add(rec)

        rec.so_tien = Decimal(total)
        rec.loai_chi_phi = loai_ten
        rec.phong_ban = "Marketing"
        rec.nguoi_chi = nguoi_chi
        rec.mo_ta = f"Tổng chi phí ADS kênh {kenh_label} tháng {thang}"
        rec.ngay = ngay_dau
        upserted += 1
        by_kenh[kenh_label] = float(total)
        total_amount += Decimal(total)

    db.commit()
    return {
        "ok": True,
        "thang": thang,
        "upserted": upserted,
        "total_amount": float(total_amount),
        "by_kenh": by_kenh,
    }
