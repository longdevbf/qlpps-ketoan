"""Auto-bridge hcns.payroll → ketoan.chi_phi_phat_sinh.

Quy ước:
- 1 row ChiPhi / (tháng × phòng ban) — gộp toàn bộ NV trong phòng.
- so_tien = SUM `payroll.luong_thuc_linh` (lương NV nhận về sau khấu trừ).
- ngay = thang-01.
- ref_payroll_thang_pb = 'PAYROLL-{thang}-{phong_ban_slug}' để idempotent.
- loai_chi_phi = 'Lương - {phong_ban}' (auto-create LoaiChiPhi nếu thiếu).
- phong_ban = phong_ban thật.
- nguoi_chi = HCNS (admin lưu bảng lương).

Gọi `sync_chi_phi_from_payroll(db, thang)` để đồng bộ. Idempotent.
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
    return "".join(out).strip("_")[:48] or "khac"


def _ensure_loai_chi_phi(db: Session, ten: str) -> str:
    existing = db.execute(
        select(LoaiChiPhi).where(LoaiChiPhi.ten == ten)
    ).scalar_one_or_none()
    if existing:
        return existing.ten
    rec = LoaiChiPhi(ten=ten, mo_ta="Auto-tạo từ hcns.payroll")
    db.add(rec)
    db.flush()
    return rec.ten


def sync_chi_phi_from_payroll(
    db: Session, thang: str, *, nguoi_chi: Optional[str] = "auto-bridge",
) -> dict:
    """Đồng bộ lương HCNS → ketoan.chi_phi cho tháng `thang` ('YYYY-MM').

    Trả `{ok, thang, upserted, total_amount, by_phong_ban: {...}}`.
    """
    try:
        from hcns.app.models import Payroll  # noqa: WPS433
    except ImportError:
        return {"ok": False, "error": "hcns.Payroll not available"}

    yr, mo = map(int, thang.split("-"))
    ngay_dau = date(yr, mo, 1)

    # Aggregate per phòng ban: SUM lương thực lĩnh + count NV
    rows = db.execute(
        select(
            Payroll.phong_ban,
            func.coalesce(func.sum(Payroll.luong_thuc_linh), 0).label("total"),
            func.count(Payroll.id).label("so_nv"),
        )
        .where(Payroll.thang == thang)
        .group_by(Payroll.phong_ban)
    ).all()

    upserted = 0
    by_phong_ban: dict[str, dict] = {}
    total_amount = Decimal(0)

    for pb, total, so_nv in rows:
        if not total:
            continue
        pb_label = (pb or "Chưa phân").strip()
        ref = f"PAYROLL-{thang}-{_slug(pb_label)}"
        loai_ten = _ensure_loai_chi_phi(db, f"Lương - {pb_label}")

        rec = db.execute(
            select(ChiPhiPhatSinh).where(ChiPhiPhatSinh.ref_payroll_thang_pb == ref)
        ).scalar_one_or_none()
        if rec is None:
            rec = ChiPhiPhatSinh(
                ngay=ngay_dau,
                ref_payroll_thang_pb=ref,
                created_by=nguoi_chi,
            )
            db.add(rec)

        rec.so_tien = Decimal(total)
        rec.loai_chi_phi = loai_ten
        rec.phong_ban = pb_label
        rec.nguoi_chi = nguoi_chi
        rec.mo_ta = f"Lương phòng {pb_label} tháng {thang} ({so_nv} NV)"
        rec.ngay = ngay_dau
        upserted += 1
        by_phong_ban[pb_label] = {"so_tien": float(total), "so_nv": int(so_nv or 0)}
        total_amount += Decimal(total)

    db.commit()
    return {
        "ok": True,
        "thang": thang,
        "upserted": upserted,
        "total_amount": float(total_amount),
        "by_phong_ban": by_phong_ban,
    }
