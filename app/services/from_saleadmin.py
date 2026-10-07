"""Bridges saleadmin → ketoan (auto-sync khi event xảy ra ở saleadmin).

Pattern: same-DB lazy-import. Idempotent qua ref_phatsinh / ref_dntt.

Hooks:
1. `sync_chi_phi_from_phatsinh(db, ps)` — saleadmin.phatsinh status='da_xu_ly'
   → ketoan.chi_phi_phat_sinh row mới (idempotent qua ref_phatsinh='PS-{id}').

2. `sync_so_quy_chi_phi_from_denghitt(db, dntt)` — saleadmin.denghitt status='duyet'
   → 1 SoQuy chi (ref_dntt='DNTT-{id}') + 1 ChiPhi phai_tra (ref_dntt='DNTT-{id}').

Cả 2 fail-soft — caller (saleadmin) không bị block nếu ketoan write fail.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional, TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ChiPhiPhatSinh, SoQuy

if TYPE_CHECKING:
    from saleadmin.app.models import PhatSinh, DeNghiTT


def sync_chi_phi_from_phatsinh(db: Session, ps: "PhatSinh") -> Optional[ChiPhiPhatSinh]:
    """saleadmin.phatsinh đã xử lý → tự ghi 1 ChiPhí.

    Idempotent qua `ref_phatsinh = 'PS-{id}'`. Nếu đã có → update so_tien/mô tả.
    """
    if ps is None or not ps.id:
        return None
    if (ps.trang_thai or "") != "da_xu_ly":
        return None  # chỉ ghi khi đã xử lý
    if not ps.so_tien or float(ps.so_tien) <= 0:
        return None  # phát sinh không gây ra chi phí (vd: ghi chú lỗi không bồi thường)

    ref = f"PS-{ps.id}"
    sp = db.begin_nested()
    try:
        rec = db.execute(
            select(ChiPhiPhatSinh).where(ChiPhiPhatSinh.ref_phatsinh == ref)
        ).scalar_one_or_none()

        loai_cp = _map_phatsinh_loai_to_chi_phi(ps.loai)
        mo_ta = (ps.mo_ta or "").strip() or f"Phát sinh {ps.loai or ''} - {ps.ma_don or ''}"

        if rec is None:
            rec = ChiPhiPhatSinh(
                ref_phatsinh=ref,
                ngay=ps.ngay or ps.created_at.date() if ps.created_at else None,
                so_tien=Decimal(ps.so_tien),
                loai_chi_phi=loai_cp,
                ma_don=ps.ma_don or None,
                mo_ta=mo_ta,
                ghi_chu=f"Auto từ phát sinh {ps.id}",
                phong_ban="Sale Admin",
                created_by="auto-bridge",
            )
            db.add(rec)
        else:
            rec.ngay = ps.ngay or rec.ngay
            rec.so_tien = Decimal(ps.so_tien)
            rec.loai_chi_phi = loai_cp
            rec.ma_don = ps.ma_don or rec.ma_don
            rec.mo_ta = mo_ta
        sp.commit()
        return rec
    except Exception:
        sp.rollback()
        return None


def sync_so_quy_chi_phi_from_denghitt(
    db: Session, dntt: "DeNghiTT", *, tai_khoan: Optional[str] = None,
) -> dict[str, Any]:
    """saleadmin.denghitt CEO duyệt → 1 SoQuy chi + 1 ChiPhí phai_tra ĐVVC.

    Idempotent qua `ref_dntt = 'DNTT-{id}'` ở cả 2 bảng.
    `tai_khoan` mặc định để None — caller có thể truyền TK rút.
    """
    out: dict[str, Any] = {"so_quy": None, "chi_phi": None}
    if dntt is None or not dntt.id:
        return out
    if (dntt.trang_thai or "") != "duyet":
        return out
    if not dntt.so_tien or float(dntt.so_tien) <= 0:
        return out

    ref = f"DNTT-{dntt.id}"
    sp = db.begin_nested()
    try:
        # 1. SoQuy chi
        sq = db.execute(
            select(SoQuy).where(SoQuy.ref_dntt == ref)
        ).scalar_one_or_none()
        # Đề nghị TT là BẢN SAO của đề xuất trả NCC bên Mua Hàng (ref_congno) thì đây là tiền trả NCC, KHÔNG phải
        # cước vận chuyển: ghi nhãn "Chi trả NCC" và KHÔNG sinh chi phí Vận chuyển. 30/09/2026: 70.000.000 trả
        # Chiến Phương bị ghi nhầm thành chi phí Vận chuyển → chi phí thừa 70tr, nợ NCC không giảm.
        ref_ncc = getattr(dntt, "ref_congno", None)
        if ref_ncc:
            noi_dung = f"Chi trả NCC {dntt.don_vi_vc or ''} — đề xuất {ref_ncc} (qua Đề nghị TT {dntt.id})".strip()
        else:
            noi_dung = f"Trả ĐVVC {dntt.don_vi_vc or ''} - đơn {dntt.ma_don or ''}".strip()
        if sq is None:
            sq = SoQuy(
                ref_dntt=ref,
                ngay=dntt.ngay_duyet.date() if dntt.ngay_duyet else (dntt.ngay_de_nghi or None),
                loai="chi",
                so_tien=Decimal(dntt.so_tien),
                tai_khoan=tai_khoan,
                noi_dung=noi_dung,
                lien_quan="denghitt",
                phan_loai_cf="tra_ncc",
                ghi_chu=f"Auto từ DNTT {dntt.id}",
                created_by="auto-bridge",
            )
            db.add(sq)
        else:
            sq.ngay = dntt.ngay_duyet.date() if dntt.ngay_duyet else sq.ngay
            sq.so_tien = Decimal(dntt.so_tien)
            sq.noi_dung = noi_dung
            if tai_khoan:
                sq.tai_khoan = tai_khoan
        out["so_quy"] = sq

        if ref_ncc:   # tiền trả NCC không phải chi phí — chỉ ghi sổ quỹ
            sp.commit()
            return out

        # 2. ChiPhí phai_tra ĐVVC
        cp = db.execute(
            select(ChiPhiPhatSinh).where(ChiPhiPhatSinh.ref_dntt == ref)
        ).scalar_one_or_none()
        mo_ta = f"Đề nghị TT {dntt.id} cho {dntt.don_vi_vc or 'ĐVVC'} - {dntt.ly_do or ''}".strip()
        if cp is None:
            cp = ChiPhiPhatSinh(
                ref_dntt=ref,
                ngay=dntt.ngay_duyet.date() if dntt.ngay_duyet else (dntt.ngay_de_nghi or None),
                so_tien=Decimal(dntt.so_tien),
                loai_chi_phi="Vận chuyển",
                don_vi_vc=dntt.don_vi_vc or None,
                ma_don=dntt.ma_don or None,
                ngan_hang=tai_khoan,
                mo_ta=mo_ta,
                ghi_chu=f"Auto từ DNTT {dntt.id}",
                phong_ban="Sale Admin",
                created_by="auto-bridge",
            )
            db.add(cp)
        else:
            cp.ngay = dntt.ngay_duyet.date() if dntt.ngay_duyet else cp.ngay
            cp.so_tien = Decimal(dntt.so_tien)
            cp.don_vi_vc = dntt.don_vi_vc or cp.don_vi_vc
            cp.ma_don = dntt.ma_don or cp.ma_don
            cp.mo_ta = mo_ta
            if tai_khoan:
                cp.ngan_hang = tai_khoan
        out["chi_phi"] = cp

        sp.commit()
        return out
    except Exception:
        sp.rollback()
        return out


def _map_phatsinh_loai_to_chi_phi(loai: Optional[str]) -> str:
    """Map saleadmin.phatsinh.loai (slug) → ketoan.chi_phi_phat_sinh.loai_chi_phi."""
    mapping = {
        "chiet_khau": "Chiết khấu / Khuyến mãi",
        "khuyen_mai": "Chiết khấu / Khuyến mãi",
        "phat":       "Phạt / Bồi thường",
        "loi_sx":     "Lỗi sản xuất",
        "khac":       "Phát sinh khác",
    }
    return mapping.get((loai or "").strip().lower(), "Phát sinh khác")
