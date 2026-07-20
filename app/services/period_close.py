"""Đóng kỳ kế toán (period close) + LN giữ lại + P&L snapshot.

Workflow `chot_ky(db, thang, by_user)`:
  1. Validate kỳ trước đã chốt (skip nếu đây là tháng đầu tiên có dữ liệu)
  2. Validate kỳ này chưa chốt
  3. Gọi `calc_pl_for_month` (M3) → snapshot vào `bao_cao_pl_snapshot`
  4. ln_giu_lai_dau_ky = ky kế trước.ln_giu_lai_cuoi_ky (default 0)
  5. cổ tức kỳ này   = SUM(von_chu_so_huu loai='chia_co_tuc' AND ngay BETWEEN tu..den)
  6. trích quỹ kỳ này = SUM(von_chu_so_huu loai='trich_quy' AND ngay BETWEEN tu..den)
  7. ln_giu_lai_cuoi_ky = ln_giu_lai_dau_ky + lnst − cổ tức − trích quỹ
  8. Insert/update ky_ke_toan (status='da_chot')
  9. Invalidate dashboard cache
  10. Return dict đầy đủ

`mo_ky(db, thang, by_user)`: reverse — chỉ admin/ceo. Cascade check kỳ sau.

`is_ky_da_chot(db, ngay)`: utility check kỳ chứa `ngay` đã chốt chưa.

Cross-app reads (von_chu_so_huu, quy_dn, inventory_movement) dùng raw SQL fail-soft.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date as date_cls, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

from ..models import BaoCaoPLSnapshot, KyKeToan


# ─── helpers ─────────────────────────────────────────────────────────────────

def _d(v: Any) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _parse_thang(thang: str) -> tuple[int, int]:
    """Parse 'YYYY-MM' → (year, month). Raise ValueError on bad format."""
    parts = thang.split("-")
    if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
        raise ValueError(f"thang không hợp lệ (cần 'YYYY-MM'): {thang!r}")
    yr = int(parts[0])
    mo = int(parts[1])
    if not (1 <= mo <= 12):
        raise ValueError(f"month không hợp lệ: {mo}")
    return yr, mo


def _month_range(thang: str) -> tuple[date_cls, date_cls]:
    yr, mo = _parse_thang(thang)
    tu = date_cls(yr, mo, 1)
    den = date_cls(yr, mo, monthrange(yr, mo)[1])
    return tu, den


def _prev_thang(thang: str) -> str:
    yr, mo = _parse_thang(thang)
    if mo == 1:
        return f"{yr - 1:04d}-12"
    return f"{yr:04d}-{mo - 1:02d}"


def _next_thang(thang: str) -> str:
    yr, mo = _parse_thang(thang)
    if mo == 12:
        return f"{yr + 1:04d}-01"
    return f"{yr:04d}-{mo + 1:02d}"


def _safe_scalar(db: Session, sql: str, default: float = 0.0, **params) -> float:
    try:
        v = db.execute(text(sql), params).scalar()
        return float(v or 0)
    except (ProgrammingError, OperationalError):
        db.rollback()
        return float(default)


# ─── tháng đầu tiên có dữ liệu ───────────────────────────────────────────────

def _ky_dau_tien_co_data(db: Session) -> Optional[str]:
    """Trả 'YYYY-MM' của ngày sớm nhất xuất hiện ở doanh_thu / chi_phi / cong_no / so_quy.

    Dùng để xác định kỳ ĐẦU TIÊN — kỳ này được phép chốt mà không cần kỳ trước đã chốt.
    Trả None nếu DB chưa có dữ liệu nào.
    """
    sql = """
        SELECT MIN(ngay)::date FROM (
            SELECT MIN(ngay) AS ngay FROM ketoan.doanh_thu
            UNION ALL
            SELECT MIN(ngay) FROM ketoan.chi_phi_phat_sinh
            UNION ALL
            SELECT MIN(ngay) FROM ketoan.cong_no
            UNION ALL
            SELECT MIN(ngay) FROM ketoan.so_quy
        ) t
        WHERE ngay IS NOT NULL
    """
    try:
        v = db.execute(text(sql)).scalar()
        if v is None:
            return None
        if isinstance(v, str):
            return v[:7]
        return v.strftime("%Y-%m")
    except (ProgrammingError, OperationalError):
        db.rollback()
        return None


# ─── P&L calculator bridge (M3) ──────────────────────────────────────────────

def _call_calc_pl_for_month(db: Session, thang: str) -> dict[str, Any]:
    """Gọi `calc_pl_for_month` của M3. Fallback dùng `_build_tong_hop` cũ + map lại
    các chỉ tiêu chuẩn mực (cho dev/test khi M3 chưa merge).

    Output dict bắt buộc có keys:
      dt_thuan, cogs, ln_gop, cp_ban_hang, cp_quan_ly,
      dt_tai_chinh, cp_tai_chinh, thu_nhap_khac, cp_khac,
      ln_truoc_thue, thue_tndn, lnst, raw_breakdown (dict).
    """
    # Try M3 import first
    try:
        from .pl_calculator import calc_pl_for_month  # type: ignore[attr-defined]
        result = calc_pl_for_month(db, thang)
        if isinstance(result, dict):
            return result
        # Pydantic model? dump
        if hasattr(result, "model_dump"):
            return result.model_dump(mode="python")
    except (ImportError, AttributeError):
        pass

    # Fallback: dùng _build_tong_hop (legacy) + map từ nhom_chi_phi nếu có
    from ..routers.bao_cao import _build_tong_hop  # noqa: WPS433

    tu, den = _month_range(thang)
    th = _build_tong_hop(db, tu, den)

    dt_thuan = _d(th.tong_doanh_thu) + _d(th.tong_don_hang_muahang)
    cogs = Decimal("0")
    ln_gop = dt_thuan - cogs

    # Phân nhóm chi phí (M3 đã backfill `nhom_chi_phi` → fail-soft)
    nhom_sql = """
        SELECT COALESCE(nhom_chi_phi, 'khac') AS nhom,
               COALESCE(SUM(so_tien), 0)::float AS tong
        FROM ketoan.chi_phi_phat_sinh
        WHERE ngay >= :tu AND ngay <= :den
        GROUP BY nhom_chi_phi
    """
    nhom_map: dict[str, float] = {}
    try:
        rows = db.execute(text(nhom_sql), {"tu": tu, "den": den}).all()
        for k, v in rows:
            nhom_map[str(k)] = float(v or 0)
    except (ProgrammingError, OperationalError):
        db.rollback()

    cp_ban_hang = _d(nhom_map.get("ban_hang", 0)) + _d(th.tong_ads_marketing)
    cp_quan_ly = _d(nhom_map.get("quan_ly", 0)) + _d(th.tong_luong_hcns) + _d(th.tong_chi_phi_co_dinh)
    cp_tai_chinh = _d(nhom_map.get("tai_chinh", 0))
    cp_khac = _d(nhom_map.get("khac", 0))

    dt_tai_chinh = Decimal("0")
    thu_nhap_khac = Decimal("0")

    ln_truoc_thue = (
        ln_gop
        - cp_ban_hang - cp_quan_ly
        + dt_tai_chinh - cp_tai_chinh
        + thu_nhap_khac - cp_khac
    )
    # Thuế TNDN 20% trên LN dương
    thue_tndn = max(Decimal("0"), ln_truoc_thue) * Decimal("0.20")
    lnst = ln_truoc_thue - thue_tndn

    return {
        "dt_thuan": dt_thuan,
        "cogs": cogs,
        "ln_gop": ln_gop,
        "cp_ban_hang": cp_ban_hang,
        "cp_quan_ly": cp_quan_ly,
        "dt_tai_chinh": dt_tai_chinh,
        "cp_tai_chinh": cp_tai_chinh,
        "thu_nhap_khac": thu_nhap_khac,
        "cp_khac": cp_khac,
        "ln_truoc_thue": ln_truoc_thue,
        "thue_tndn": thue_tndn,
        "lnst": lnst,
        "raw_breakdown": {
            "fallback": True,
            "tong_doanh_thu": float(th.tong_doanh_thu),
            "tong_don_hang_muahang": float(th.tong_don_hang_muahang),
            "tong_chi_phi_phat_sinh": float(th.tong_chi_phi_phat_sinh),
            "tong_chi_phi_co_dinh": float(th.tong_chi_phi_co_dinh),
            "tong_luong_hcns": float(th.tong_luong_hcns),
            "tong_ads_marketing": float(th.tong_ads_marketing),
            "nhom_chi_phi": nhom_map,
        },
    }


# ─── cổ tức + trích quỹ (M4 voncsh, fail-soft) ───────────────────────────────

def _sum_voncsh_loai(
    db: Session, loai: str, tu: date_cls, den: date_cls,
) -> float:
    """SUM(von_chu_so_huu.so_tien WHERE loai_giao_dich=? AND ngay BETWEEN tu..den)."""
    # M4 column tên `loai_giao_dich` (theo migration m4_voncsh)
    sql = """
        SELECT COALESCE(SUM(so_tien), 0)::float
        FROM ketoan.von_chu_so_huu
        WHERE loai_giao_dich = :loai AND ngay >= :tu AND ngay <= :den
    """
    return _safe_scalar(db, sql, tu=tu, den=den, loai=loai)


# ─── invalidate dashboard cache (fail-soft) ──────────────────────────────────

def _invalidate_dashboard_cache(thang: Optional[str] = None) -> None:
    try:
        from ..routers.bao_cao import invalidate_dashboard_cache
        invalidate_dashboard_cache(thang)
    except Exception:
        pass


# ─── public API ──────────────────────────────────────────────────────────────

class PeriodCloseError(Exception):
    """Lỗi domain khi chốt/mở kỳ — router sẽ map sang HTTP 409/400."""
    def __init__(self, message: str, code: str = "period_close_error", status_code: int = 409):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def chot_ky(db: Session, thang: str, by_user: str) -> dict[str, Any]:
    """Chốt kỳ kế toán tháng `thang` ('YYYY-MM').

    Returns dict đầy đủ snapshot + LN giữ lại đầu/cuối kỳ.
    Raise PeriodCloseError nếu vi phạm rule.
    """
    _parse_thang(thang)  # validate format (raises ValueError)
    tu, den = _month_range(thang)

    # 1. Kỳ này đã chốt chưa?
    ky = db.get(KyKeToan, thang)
    if ky and ky.trang_thai == "da_chot":
        raise PeriodCloseError(
            f"Kỳ {thang} đã được chốt lúc {ky.chot_luc} bởi {ky.chot_boi or 'unknown'}",
            code="ky_da_chot", status_code=409,
        )

    # 2. Kỳ trước phải đã chốt (trừ khi đây là kỳ đầu tiên)
    ky_dau = _ky_dau_tien_co_data(db)
    if ky_dau is not None and thang > ky_dau:
        prev = _prev_thang(thang)
        prev_ky = db.get(KyKeToan, prev)
        if prev_ky is None or prev_ky.trang_thai != "da_chot":
            raise PeriodCloseError(
                f"Kỳ trước ({prev}) chưa được chốt — phải chốt tuần tự",
                code="ky_truoc_chua_chot", status_code=409,
            )

    # 3. Tính P&L kỳ này
    pl = _call_calc_pl_for_month(db, thang)

    # Upsert P&L snapshot theo `thang` (UNIQUE)
    snap = db.execute(
        select(BaoCaoPLSnapshot).where(BaoCaoPLSnapshot.thang == thang)
    ).scalar_one_or_none()
    if snap is None:
        snap = BaoCaoPLSnapshot(thang=thang)
        db.add(snap)
    snap.dt_thuan = _d(pl.get("dt_thuan"))
    snap.cogs = _d(pl.get("cogs"))
    snap.ln_gop = _d(pl.get("ln_gop"))
    snap.cp_ban_hang = _d(pl.get("cp_ban_hang"))
    snap.cp_quan_ly = _d(pl.get("cp_quan_ly"))
    snap.dt_tai_chinh = _d(pl.get("dt_tai_chinh"))
    snap.cp_tai_chinh = _d(pl.get("cp_tai_chinh"))
    snap.thu_nhap_khac = _d(pl.get("thu_nhap_khac"))
    snap.cp_khac = _d(pl.get("cp_khac"))
    snap.ln_truoc_thue = _d(pl.get("ln_truoc_thue"))
    snap.thue_tndn = _d(pl.get("thue_tndn"))
    snap.lnst = _d(pl.get("lnst"))
    raw = pl.get("raw_breakdown")
    snap.raw_breakdown = raw if isinstance(raw, dict) else {"raw": str(raw)}
    db.flush()

    # 4. LN giữ lại đầu kỳ = kỳ trước.ln_giu_lai_cuoi_ky (default 0)
    prev_thang = _prev_thang(thang)
    prev_ky = db.get(KyKeToan, prev_thang)
    ln_dau_ky = _d(prev_ky.ln_giu_lai_cuoi_ky) if (prev_ky and prev_ky.ln_giu_lai_cuoi_ky is not None) else Decimal("0")

    # 5. Cổ tức + 6. Trích quỹ kỳ này (fail-soft từ M4)
    co_tuc = _d(_sum_voncsh_loai(db, "chia_co_tuc", tu, den))
    trich_quy = _d(_sum_voncsh_loai(db, "trich_quy", tu, den))

    lnst = _d(snap.lnst)
    # 7. LN giữ lại cuối kỳ
    ln_cuoi_ky = ln_dau_ky + lnst - co_tuc - trich_quy

    # 8. Upsert ky_ke_toan
    now = datetime.now(timezone.utc)
    if ky is None:
        ky = KyKeToan(thang=thang)
        db.add(ky)
    ky.trang_thai = "da_chot"
    ky.chot_luc = now
    ky.chot_boi = by_user
    ky.pl_snapshot_id = snap.id
    ky.ln_giu_lai_dau_ky = ln_dau_ky
    ky.lnst_ky = lnst
    ky.ln_giu_lai_cuoi_ky = ln_cuoi_ky
    ky.co_tuc_da_chia = co_tuc
    ky.trich_quy_ky = trich_quy

    db.commit()
    db.refresh(ky)
    db.refresh(snap)

    # 9. Invalidate dashboard cache
    _invalidate_dashboard_cache(thang)

    # 10. Return
    return {
        "ok": True,
        "thang": thang,
        "trang_thai": ky.trang_thai,
        "pl_snapshot_id": snap.id,
        "ln_giu_lai_dau_ky": ln_dau_ky,
        "lnst_ky": lnst,
        "co_tuc_da_chia": co_tuc,
        "trich_quy_ky": trich_quy,
        "ln_giu_lai_cuoi_ky": ln_cuoi_ky,
        "chot_luc": ky.chot_luc,
        "chot_boi": ky.chot_boi,
        "snapshot": {
            "id": snap.id,
            "dt_thuan": float(snap.dt_thuan or 0),
            "cogs": float(snap.cogs or 0),
            "ln_gop": float(snap.ln_gop or 0),
            "cp_ban_hang": float(snap.cp_ban_hang or 0),
            "cp_quan_ly": float(snap.cp_quan_ly or 0),
            "dt_tai_chinh": float(snap.dt_tai_chinh or 0),
            "cp_tai_chinh": float(snap.cp_tai_chinh or 0),
            "thu_nhap_khac": float(snap.thu_nhap_khac or 0),
            "cp_khac": float(snap.cp_khac or 0),
            "ln_truoc_thue": float(snap.ln_truoc_thue or 0),
            "thue_tndn": float(snap.thue_tndn or 0),
            "lnst": float(snap.lnst or 0),
            "raw_breakdown": snap.raw_breakdown,
        },
    }


def mo_ky(db: Session, thang: str, by_user: str) -> dict[str, Any]:
    """Mở lại kỳ đã chốt (admin only — caller check role).

    Cascade: nếu kỳ T+1, T+2, ... đã chốt → raise 409 (yêu cầu mở lần lượt từ kỳ
    mới nhất xuống). Xoá snapshot P&L của kỳ này + reset ky_ke_toan về 'dang_mo'.
    """
    _parse_thang(thang)  # validate format

    ky = db.get(KyKeToan, thang)
    if ky is None or ky.trang_thai != "da_chot":
        raise PeriodCloseError(
            f"Kỳ {thang} chưa được chốt nên không cần mở",
            code="ky_chua_chot", status_code=409,
        )

    # Cascade: tháng sau phải mở trước
    nxt = _next_thang(thang)
    nxt_ky = db.get(KyKeToan, nxt)
    if nxt_ky is not None and nxt_ky.trang_thai == "da_chot":
        raise PeriodCloseError(
            f"Kỳ sau ({nxt}) đã chốt — vui lòng mở lại kỳ sau trước",
            code="ky_sau_da_chot", status_code=409,
        )

    snap_id = ky.pl_snapshot_id

    # Reset trạng thái + xoá snapshot
    ky.trang_thai = "dang_mo"
    ky.chot_luc = None
    ky.chot_boi = None
    ky.pl_snapshot_id = None
    ky.lnst_ky = None
    ky.ln_giu_lai_cuoi_ky = None
    ky.co_tuc_da_chia = Decimal("0")
    ky.trich_quy_ky = Decimal("0")

    if snap_id is not None:
        snap = db.get(BaoCaoPLSnapshot, snap_id)
        if snap is not None:
            db.delete(snap)

    db.commit()
    _invalidate_dashboard_cache(thang)

    return {
        "ok": True, "thang": thang, "trang_thai": "dang_mo",
        "mo_boi": by_user,
        "snapshot_da_xoa": snap_id,
    }


def is_ky_da_chot(db: Session, ngay: date_cls) -> bool:
    """True nếu kỳ chứa `ngay` đã ở trạng thái 'da_chot'."""
    thang = ngay.strftime("%Y-%m")
    ky = db.get(KyKeToan, thang)
    return bool(ky and ky.trang_thai == "da_chot")


def get_ln_giu_lai_luy_ke(db: Session) -> dict[str, Any]:
    """LN giữ lại lũy kế hiện tại = kỳ chốt mới nhất.ln_giu_lai_cuoi_ky.

    Trả {ky_chot_moi_nhat, ln_giu_lai_luy_ke, n_ky_da_chot}.
    """
    rows = db.execute(
        select(KyKeToan)
        .where(KyKeToan.trang_thai == "da_chot")
        .order_by(KyKeToan.thang.desc())
    ).scalars().all()
    if not rows:
        return {
            "ky_chot_moi_nhat": None,
            "ln_giu_lai_luy_ke": Decimal("0"),
            "n_ky_da_chot": 0,
        }
    latest = rows[0]
    return {
        "ky_chot_moi_nhat": latest.thang,
        "ln_giu_lai_luy_ke": _d(latest.ln_giu_lai_cuoi_ky),
        "n_ky_da_chot": len(rows),
    }
