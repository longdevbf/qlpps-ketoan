"""Báo Cáo Kết Quả Kinh Doanh (P&L / Income Statement).

Endpoints:
  - GET /api/bao-cao/pl?thang=YYYY-MM        → P&L tháng (M3 — chuẩn breakdown)
  - GET /api/bao-cao/pl/yearly?nam=YYYY      → loop 12 tháng + tổng hợp năm
  - GET /api/bao-cao/pnl?from&to&compare=1   → legacy waterfall theo khoảng (giữ BC)

P&L tháng đi qua `services.pl_calculator.calc_pl_for_month()` (chuẩn nhom_chi_phi).

Cache: in-process TTL 30s key theo thang/nam (giống pattern `bao_cao.py`).
"""
from __future__ import annotations

import time
from datetime import date as date_cls, timedelta
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from shared.auth import JWTPayload
from shared.db import get_db

from ..models import ChiPhiPhatSinh, DoanhThu
from ..services import calc_pl_for_month
from ..services.pl_calculator import NHOM_DINH_PHI_PL, dinh_phi_phan_bo_thang
from ..services.pl_chi_tiet import (
    KHOAN as KHOAN_PL,
    SO_DONG_MAC_DINH,
    SO_DONG_TOI_DA,
    chi_tiet as chi_tiet_dong_pl,
)
from ..services.loi_doc import bat_dau_ghi_loi
from ..services.nguon_bao_cao import NGUON_KQKD
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


# ─── Constants ────────────────────────────────────────────────────────────────

TAX_RATE = 0.20                 # Thuế TNDN 20%
COGS_FALLBACK_RATIO = 0.60      # Khi không có PO Hoàn Thành → ước tính 60% DT
EXCLUDED_LOAI_CHI_PHI_QUANLY = ("Marketing", "Quảng cáo", "Quảng Cáo", "Quang cao", "Ads")
# Lãi vay ghi ở chi_phi_phat_sinh phải loại khỏi "chi phí quản lý" — đã tính riêng ở
# _chi_phi_tai_chinh() (mã 22). Không loại sẽ đếm 2 lần cùng 1 khoản lãi vay thật
# (bug thật phát hiện 2026-09-25: kỳ 05/2026 đếm trùng ~751.7tr do dữ liệu vừa ghi ở
# ketoan.khoan_vay_giao_dich VỪA ghi lại ở ketoan.chi_phi_phat_sinh).
EXCLUDED_LOAI_CHI_PHI_LAI_VAY = ("Lãi vay", "Thanh Toán Lãi Vay", "Thanh toán lãi vay", "Lai vay")


# In-process TTL cache cho /pl + /pl/yearly (30s)
_PL_CACHE: dict[str, tuple[float, dict]] = {}
_PL_TTL = 30.0


def invalidate_pl_cache(key: Optional[str] = None) -> None:
    """Clear PL cache. Gọi từ CRUD chi_phi/doanh_thu nếu cần invalidate sớm."""
    if key is None:
        _PL_CACHE.clear()
    else:
        _PL_CACHE.pop(key, None)


def _cache_get(key: str) -> Optional[dict]:
    now = time.time()
    cached = _PL_CACHE.get(key)
    if cached and (now - cached[0]) < _PL_TTL:
        return cached[1]
    return None


def _cache_set(key: str, value: dict) -> None:
    _PL_CACHE[key] = (time.time(), value)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _resolve_range(
    tu: Optional[date_cls], den: Optional[date_cls]
) -> tuple[date_cls, date_cls]:
    """Default: tháng hiện tại (1 → today)."""
    today = date_cls.today()
    if not den:
        den = today
    if not tu:
        tu = today.replace(day=1)
    if tu > den:
        tu, den = den, tu
    return tu, den


def _previous_range(tu: date_cls, den: date_cls) -> tuple[date_cls, date_cls]:
    """Trả khoảng kỳ trước cùng độ dài: (tu - n, tu - 1) với n = (den-tu+1)."""
    n_days = (den - tu).days + 1
    prev_den = tu - timedelta(days=1)
    prev_tu = prev_den - timedelta(days=n_days - 1)
    return prev_tu, prev_den


_NHAN_NHOM = {"ban_hang": "bán hàng", "quan_ly": "quản lý"}


def _months_in_range(tu: date_cls, den: date_cls) -> list[str]:
    """List 'YYYY-MM' từ tu → den (inclusive)."""
    out: list[str] = []
    y, m = tu.year, tu.month
    while (y, m) <= (den.year, den.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _safe_rows(db: Session, sql: str, **params) -> list[Any]:
    """Run query; rollback + trả [] khi schema chưa có."""
    try:
        return db.execute(text(sql), params).all()
    except (ProgrammingError, OperationalError):
        db.rollback()
        return []


def _safe_scalar(db: Session, sql: str, default: float = 0.0, **params) -> float:
    """Run scalar query; trả default khi schema chưa có."""
    try:
        v = db.execute(text(sql), params).scalar()
        return float(v or 0)
    except (ProgrammingError, OperationalError):
        db.rollback()
        return default


def _pct(num: float, den: float) -> float:
    """Return (num/den * 100) rounded 2dp; 0 if den == 0."""
    if not den:
        return 0.0
    return round((num / den) * 100, 2)


def _delta_pct(curr: float, prev: float) -> float:
    """% change vs prev. 0 nếu prev = 0 và curr = 0; cap ±999.99 khi prev=0."""
    if not prev:
        if not curr:
            return 0.0
        return 999.99 if curr > 0 else -999.99
    return round((curr - prev) / abs(prev) * 100, 2)


# ─── Section calculators (legacy /pnl) ───────────────────────────────────────

def _doanh_thu(db: Session, tu: date_cls, den: date_cls) -> dict[str, Any]:
    """Tổng doanh thu + breakdown by loai_thanh_toan (Đặt Cọc / Thanh Toán / ...)."""
    total = float(
        db.execute(
            select(func.coalesce(func.sum(DoanhThu.so_tien), 0))
            .where(DoanhThu.ngay >= tu, DoanhThu.ngay <= den)
        ).scalar()
        or 0
    )

    rows = db.execute(
        select(
            func.coalesce(DoanhThu.loai_thanh_toan, "Khác"),
            func.coalesce(func.sum(DoanhThu.so_tien), 0),
        )
        .where(DoanhThu.ngay >= tu, DoanhThu.ngay <= den)
        .group_by(DoanhThu.loai_thanh_toan)
        .order_by(func.sum(DoanhThu.so_tien).desc())
    ).all()
    items = [{"loai": str(k or "Khác"), "so_tien": float(v or 0)} for k, v in rows]

    return {"total": total, "items": items}


def _gia_von(db: Session, tu: date_cls, den: date_cls, doanh_thu_total: float) -> dict[str, Any]:
    """COGS legacy: ưu tiên ketoan.inventory_movement (M1), fallback muahang.purchase_orders,
    fallback ước tính 60% DT."""
    # Nguồn 1: inventory_movement (sprint M1)
    sql_inv = """
        SELECT COALESCE(SUM(thanh_tien), 0)
        FROM ketoan.inventory_movement
        WHERE loai = 'xuat'
          AND ngay >= :tu AND ngay <= :den
    """
    inv_total = _safe_scalar(db, sql_inv, tu=tu, den=den)
    if inv_total > 0:
        return {"total": inv_total, "source": "inventory_movement", "note": None}

    sql_po = """
        SELECT COALESCE(SUM(
            CASE
              WHEN selected_ncc_id IS NOT NULL
                   AND ncc_totals IS NOT NULL
                   AND (ncc_totals ->> selected_ncc_id) IS NOT NULL
              THEN (ncc_totals ->> selected_ncc_id)::numeric
              WHEN comparison_best_ncc IS NOT NULL
                   AND ncc_totals IS NOT NULL
                   AND (ncc_totals ->> comparison_best_ncc) IS NOT NULL
              THEN (ncc_totals ->> comparison_best_ncc)::numeric
              ELSE 0
            END
        ), 0)
        FROM muahang.purchase_orders
        WHERE status = 'Hoàn Thành'
          AND COALESCE(ngay_dat_xuong, created_at::date) >= :tu
          AND COALESCE(ngay_dat_xuong, created_at::date) <= :den
    """
    po_total = _safe_scalar(db, sql_po, tu=tu, den=den)
    if po_total > 0:
        return {"total": po_total, "source": "muahang_po", "note": None}

    estimate = round(doanh_thu_total * COGS_FALLBACK_RATIO, 2)
    return {
        "total": estimate,
        "source": "estimate",
        "note": (
            f"Ước tính {int(COGS_FALLBACK_RATIO * 100)}% doanh thu "
            "(không có inventory_movement / PO Hoàn Thành trong kỳ)"
        ),
    }


def _chi_phi_ban_hang(db: Session, tu: date_cls, den: date_cls) -> dict[str, Any]:
    """Chi phí bán hàng = ads marketing trong kỳ. Group by kenh."""
    sql_total = """
        SELECT COALESCE(SUM(chi_phi), 0)
        FROM marketing.ads_cost
        WHERE ngay >= :tu AND ngay <= :den
    """
    total = _safe_scalar(db, sql_total, tu=tu, den=den)

    sql_breakdown = """
        SELECT COALESCE(kenh, 'Khác') AS kenh,
               COALESCE(SUM(chi_phi), 0) AS so_tien
        FROM marketing.ads_cost
        WHERE ngay >= :tu AND ngay <= :den
        GROUP BY kenh
        ORDER BY 2 DESC
    """
    rows = _safe_rows(db, sql_breakdown, tu=tu, den=den)
    items = [{"kenh": str(k or "Khác"), "so_tien": float(v or 0)} for k, v in rows]
    return {"total": total, "items": items}


def _luong(db: Session, tu: date_cls, den: date_cls) -> dict[str, Any]:
    """Tổng lương HCNS theo từng tháng giao với khoảng [tu, den]."""
    months = _months_in_range(tu, den)
    if not months:
        return {"total": 0.0, "thang_count": 0, "n_nv": 0, "by_thang": []}

    placeholders = ",".join(f":m{i}" for i in range(len(months)))
    params: dict[str, Any] = {f"m{i}": v for i, v in enumerate(months)}
    sql_total = f"""
        SELECT COALESCE(SUM(luong_thuc_linh), 0),
               COUNT(DISTINCT ma_nv)
        FROM hcns.payroll
        WHERE thang IN ({placeholders})
    """
    try:
        row = db.execute(text(sql_total), params).first()
        total = float((row[0] if row else 0) or 0)
        n_nv = int((row[1] if row else 0) or 0)
    except (ProgrammingError, OperationalError):
        db.rollback()
        total, n_nv = 0.0, 0

    sql_by = f"""
        SELECT thang, COALESCE(SUM(luong_thuc_linh), 0)
        FROM hcns.payroll
        WHERE thang IN ({placeholders})
        GROUP BY thang
        ORDER BY thang
    """
    rows = _safe_rows(db, sql_by, **params)
    by_thang = [{"thang": str(k), "so_tien": float(v or 0)} for k, v in rows]

    return {
        "total": total,
        "thang_count": len(months),
        "n_nv": n_nv,
        "by_thang": by_thang,
    }


def _dinh_phi(db: Session, tu: date_cls, den: date_cls) -> dict[str, Any]:
    """Định phí phân bổ theo ĐÚNG cách của KQKD (pl_calculator.dinh_phi_phan_bo_thang —
    tôn trọng so_thang_phan_bo) cho từng tháng chạm khoảng, mỗi tháng tính trọn tháng.

    QA 25/09/2026: bản trước lấy so_tien_thang × số tháng overlap, bỏ qua so_thang_phan_bo
    → "Thuê showroom T6–8" 127,5tr/3 tháng bị cộng nguyên 127,5tr MỖI tháng (kể cả sau T8).
    `items` nay là từng (tháng, nhóm) có số — không còn từng dòng chi_phi_co_dinh.
    """
    months_in = _months_in_range(tu, den)
    items: list[dict[str, Any]] = []
    for thang in months_in:
        pb = dinh_phi_phan_bo_thang(db, thang)
        for nhom in NHOM_DINH_PHI_PL:
            if pb[nhom]:
                items.append({
                    "thang": thang, "nhom": nhom,
                    "loai_chi_phi": f"Định phí {_NHAN_NHOM.get(nhom, nhom)} {thang}",
                    "so_tien": pb[nhom],
                })
    total = round(sum(x["so_tien"] for x in items), 2)
    items.sort(key=lambda x: x["so_tien"], reverse=True)
    return {"total": total, "items": items, "n_months": len(months_in)}


def _bien_phi(db: Session, tu: date_cls, den: date_cls) -> dict[str, Any]:
    """Biến phí KT trong kỳ, loại trừ Marketing/Quảng cáo (đã ở chi_phi_ban_hang)
    và Lãi vay (đã tính riêng ở _chi_phi_tai_chinh — mã 22)."""
    excluded = list(EXCLUDED_LOAI_CHI_PHI_QUANLY) + list(EXCLUDED_LOAI_CHI_PHI_LAI_VAY)
    total = float(
        db.execute(
            select(func.coalesce(func.sum(ChiPhiPhatSinh.so_tien), 0))
            .where(ChiPhiPhatSinh.ngay >= tu, ChiPhiPhatSinh.ngay <= den)
            .where(
                func.coalesce(ChiPhiPhatSinh.loai_chi_phi, "").notin_(excluded)
            )
        ).scalar()
        or 0
    )

    rows = db.execute(
        select(
            func.coalesce(ChiPhiPhatSinh.loai_chi_phi, "Khác"),
            func.coalesce(func.sum(ChiPhiPhatSinh.so_tien), 0),
        )
        .where(ChiPhiPhatSinh.ngay >= tu, ChiPhiPhatSinh.ngay <= den)
        .where(
            func.coalesce(ChiPhiPhatSinh.loai_chi_phi, "").notin_(excluded)
        )
        .group_by(ChiPhiPhatSinh.loai_chi_phi)
        .order_by(func.sum(ChiPhiPhatSinh.so_tien).desc())
    ).all()
    items = [{"loai": str(k or "Khác"), "so_tien": float(v or 0)} for k, v in rows]

    return {"total": round(total, 2), "items": items}


def _chi_phi_tai_chinh(db: Session, tu: date_cls, den: date_cls) -> dict[str, Any]:
    """Chi phí tài chính = lãi vay đã trả trong kỳ.

    Nguồn 1 (chuẩn): ketoan.khoan_vay_giao_dich (loai=tra_lai/tra_goc_lai) — sổ vay thật.
    Nguồn 2: ketoan.chi_phi_phat_sinh có loai_chi_phi ∈ EXCLUDED_LOAI_CHI_PHI_LAI_VAY —
    nhiều khoản lãi vay được KT ghi trực tiếp ở đây thay vì qua sổ vay (vd 07-08/2026
    không có giao dịch nào ở khoan_vay_giao_dich dù thực trả lãi). `_bien_phi()` đã loại
    các dòng này khỏi "chi phí quản lý" để khỏi đếm 2 lần — nên phải cộng chúng lại ở
    đây, KHÔNG được bỏ sót.

    Dùng MAX(nguồn 1, nguồn 2) thay vì CỘNG: 2 nguồn có thể ghi TRÙNG cùng 1 khoản lãi
    vay thật (bug thật phát hiện 2026-09-25 — kỳ 05/2026 cả 2 bảng cùng ghi các khoản
    lãi vay VPBank giống hệt ngày + số tiền) — cộng thẳng sẽ đếm trùng; lấy MAX coi
    nguồn nào ghi đầy đủ hơn trong kỳ là số đúng (cùng nguyên tắc `_max_pos` đã dùng ở
    bao_cao_can_doi.py cho vấn đề tương tự).
    """
    sql_vay = """
        SELECT COALESCE(SUM(
            CASE
                WHEN gd.loai = 'tra_lai' THEN gd.so_tien
                WHEN gd.loai = 'tra_goc_lai' THEN COALESCE(gd.so_tien_lai, 0)
                ELSE 0
            END
        ), 0)
        FROM ketoan.khoan_vay_giao_dich gd
        WHERE gd.ngay >= :tu AND gd.ngay <= :den
    """
    total_vay = _safe_scalar(db, sql_vay, tu=tu, den=den)

    sql_breakdown = """
        SELECT kv.nguon_vay AS nguon,
               COALESCE(SUM(
                   CASE
                       WHEN gd.loai = 'tra_lai' THEN gd.so_tien
                       WHEN gd.loai = 'tra_goc_lai' THEN COALESCE(gd.so_tien_lai, 0)
                       ELSE 0
                   END
               ), 0) AS so_tien
        FROM ketoan.khoan_vay_giao_dich gd
        JOIN ketoan.khoan_vay kv ON kv.id = gd.khoan_vay_id
        WHERE gd.ngay >= :tu AND gd.ngay <= :den
        GROUP BY kv.nguon_vay
        HAVING SUM(
            CASE
                WHEN gd.loai = 'tra_lai' THEN gd.so_tien
                WHEN gd.loai = 'tra_goc_lai' THEN COALESCE(gd.so_tien_lai, 0)
                ELSE 0
            END
        ) > 0
        ORDER BY 2 DESC
    """
    rows_vay = _safe_rows(db, sql_breakdown, tu=tu, den=den)

    placeholders = ",".join(f":lv{i}" for i in range(len(EXCLUDED_LOAI_CHI_PHI_LAI_VAY)))
    lv_params = {f"lv{i}": v for i, v in enumerate(EXCLUDED_LOAI_CHI_PHI_LAI_VAY)}
    sql_phat_sinh = f"""
        SELECT COALESCE(SUM(so_tien), 0)
        FROM ketoan.chi_phi_phat_sinh
        WHERE ngay >= :tu AND ngay <= :den
          AND loai_chi_phi IN ({placeholders})
    """
    total_phat_sinh = _safe_scalar(db, sql_phat_sinh, tu=tu, den=den, **lv_params)

    sql_phat_sinh_breakdown = f"""
        SELECT COALESCE(NULLIF(ten_khoan, ''), loai_chi_phi) AS nguon, so_tien
        FROM ketoan.chi_phi_phat_sinh
        WHERE ngay >= :tu AND ngay <= :den
          AND loai_chi_phi IN ({placeholders})
        ORDER BY so_tien DESC
    """
    rows_phat_sinh = _safe_rows(db, sql_phat_sinh_breakdown, tu=tu, den=den, **lv_params)

    if total_phat_sinh > total_vay:
        total = total_phat_sinh
        items = [{"nguon": str(k or "Khác"), "so_tien": float(v or 0)} for k, v in rows_phat_sinh]
    else:
        total = total_vay
        items = [{"nguon": str(k or "Khác"), "so_tien": float(v or 0)} for k, v in rows_vay]
    return {"total": total, "items": items}


def _build_pnl(db: Session, tu: date_cls, den: date_cls) -> dict[str, Any]:
    """Tính P&L 1 kỳ → dict đầy đủ các tầng + margins (legacy /pnl)."""
    dt = _doanh_thu(db, tu, den)
    gv = _gia_von(db, tu, den, dt["total"])
    ln_gop = round(dt["total"] - gv["total"], 2)

    cp_bh = _chi_phi_ban_hang(db, tu, den)
    ln_hd_ban = round(ln_gop - cp_bh["total"], 2)

    cp_tc = _chi_phi_tai_chinh(db, tu, den)
    ln_hd_kd = round(ln_hd_ban - cp_tc["total"], 2)

    luong = _luong(db, tu, den)
    dinh_phi = _dinh_phi(db, tu, den)
    bien_phi = _bien_phi(db, tu, den)
    cp_ql_total = round(luong["total"] + dinh_phi["total"] + bien_phi["total"], 2)

    ln_truoc_thue = round(ln_hd_kd - cp_ql_total, 2)
    thue = round(max(0.0, ln_truoc_thue * TAX_RATE), 2)
    ln_sau_thue = round(ln_truoc_thue - thue, 2)

    return {
        "from": str(tu),
        "to": str(den),
        "doanh_thu": dt,
        "gia_von": gv,
        "loi_nhuan_gop": ln_gop,
        "chi_phi_ban_hang": cp_bh,
        "loi_nhuan_hd_ban": ln_hd_ban,
        "chi_phi_tai_chinh": cp_tc,
        "loi_nhuan_hd_kd": ln_hd_kd,
        "chi_phi_quan_ly": {
            "total": cp_ql_total,
            "luong": luong,
            "dinh_phi": dinh_phi,
            "bien_phi": bien_phi,
        },
        "loi_nhuan_truoc_thue": ln_truoc_thue,
        "thue_tndn": thue,
        "loi_nhuan_sau_thue": ln_sau_thue,
        "margins": {
            "gross": _pct(ln_gop, dt["total"]),
            "operating": _pct(ln_hd_kd, dt["total"]),
            "net": _pct(ln_sau_thue, dt["total"]),
        },
    }


# ─── M3 Endpoints — /pl + /pl/yearly ─────────────────────────────────────────

def _validate_thang(thang: str) -> str:
    """Validate format YYYY-MM."""
    try:
        y, m = thang.split("-")
        yy, mm = int(y), int(m)
        if mm < 1 or mm > 12 or yy < 2000 or yy > 2100:
            raise ValueError
    except (ValueError, IndexError):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"thang phải dạng YYYY-MM, nhận: {thang!r}",
        )
    return f"{yy:04d}-{mm:02d}"


@router.get("/pl")
def bao_cao_pl_thang(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    thang: str = Query(..., description="YYYY-MM"),
):
    """Báo cáo lãi lỗ tháng — phân loại theo nhom_chi_phi (chuẩn M3)."""
    thang = _validate_thang(thang)
    cache_key = f"pl:{thang}"
    cached = _cache_get(cache_key)
    if cached:
        return {**cached, "nguon": NGUON_KQKD}
    loi_doc = bat_dau_ghi_loi()
    result = calc_pl_for_month(db, thang)
    # Đợt 1 (07/10/2026): bảng/cột không đọc được → trả kèm danh sách. Vẫn cache như cũ (lưu kèm danh
    # sách lỗi) — nếu bỏ cache thì một bảng CỐ Ý chưa có (nhánh dự phòng) sẽ làm KQKD tính lại mỗi lần
    # mở trang. `nguon` là mô tả tĩnh nên gắn sau cache.
    if loi_doc:
        result = {**result, "loi_doc_du_lieu": loi_doc}
    _cache_set(cache_key, result)
    return {**result, "nguon": NGUON_KQKD}


@router.get("/pl/chi-tiet")
def bao_cao_pl_chi_tiet(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    khoa: str = Query(..., description="Khoá dòng KQKD, vd 'cogs', 'cp_tai_chinh.lai_vay'"),
    tu: date_cls = Query(..., description="Từ ngày"),
    den: date_cls = Query(..., description="Đến ngày"),
    trang: int = Query(1, ge=1),
    so_dong: int = Query(SO_DONG_MAC_DINH, ge=1, le=SO_DONG_TOI_DA),
):
    """Các chứng từ gốc làm nên một dòng Kết quả kinh doanh — cho popup "số này ở đâu ra".

    Dùng CHUNG mệnh đề WHERE với hàm tính số tổng (xem `services/pl_chi_tiet.py`) nên
    `tong` trả về luôn bằng số đang hiện trên dòng. Có phân trang vì có khoản lên tới
    hàng trăm chứng từ; `tong` và `so_dong` vẫn tính trên toàn bộ, không theo trang.

    Khoá chưa khai (định phí phân bổ, lương, ads) trả 404 kèm danh sách khoá đang có —
    thà báo không biết còn hơn trả số đoán.
    """
    if den < tu:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Ngày 'đến' phải từ ngày 'từ' trở đi",
        )
    kq = chi_tiet_dong_pl(db, khoa, tu, den, trang=trang, so_dong=so_dong)
    if kq is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, {
            "loi": "khoa_chua_khai",
            "thong_bao": f"Chưa có chi tiết cho dòng '{khoa}'.",
            "khoa_dang_co": sorted(KHOAN_PL.keys()),
        })
    return kq


@router.get("/pl/yearly")
def bao_cao_pl_yearly(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    nam: int = Query(..., ge=2000, le=2100),
):
    """Loop 12 tháng năm `nam` → trả từng tháng + tổng năm.

    Tổng năm = sum(các tháng) cho mỗi key số.
    """
    cache_key = f"pl_yearly:{nam}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    months: list[dict[str, Any]] = []
    # Phase 4: cp_ban_hang/cp_quan_ly/cp_tai_chinh giờ là dict — dùng .tong
    SCALAR_KEYS = (
        "dt_thuan", "cogs", "ln_gop",
        "dt_tai_chinh", "thu_nhap_khac", "cp_khac",
        "ln_thuan_hdkd",
        "ln_truoc_thue", "thue_tndn", "lnst",
    )
    DICT_TONG_KEYS = ("cp_ban_hang", "cp_quan_ly", "cp_tai_chinh")
    nam_total: dict[str, float] = {k: 0.0 for k in SCALAR_KEYS}
    for k in DICT_TONG_KEYS:
        nam_total[k] = 0.0

    for m in range(1, 13):
        thang = f"{nam:04d}-{m:02d}"
        pl = calc_pl_for_month(db, thang)
        months.append(pl)
        for k in SCALAR_KEYS:
            nam_total[k] = round(nam_total[k] + float(pl.get(k, 0) or 0), 2)
        for k in DICT_TONG_KEYS:
            v = pl.get(k, 0)
            if isinstance(v, dict):
                v = v.get("tong", 0) or 0
            nam_total[k] = round(nam_total[k] + float(v or 0), 2)

    # Khi tính cả năm: thuế TNDN nên được re-tính trên LNTT cả năm
    # (tính tháng lẻ có thể méo do tháng âm bù tháng dương).
    nam_lntt = round(
        nam_total["ln_gop"]
        - nam_total["cp_ban_hang"]
        - nam_total["cp_quan_ly"]
        - nam_total["cp_tai_chinh"]
        + nam_total["dt_tai_chinh"]
        + nam_total["thu_nhap_khac"]
        - nam_total["cp_khac"],
        2,
    )
    nam_thue = round(nam_lntt * TAX_RATE, 2) if nam_lntt > 0 else 0.0
    nam_total["ln_truoc_thue"] = nam_lntt
    nam_total["thue_tndn"] = nam_thue
    nam_total["lnst"] = round(nam_lntt - nam_thue, 2)

    result = {
        "nam": nam,
        "months": months,
        "yearly_total": nam_total,
    }
    _cache_set(cache_key, result)
    return result


# ─── Legacy endpoint /pnl (giữ backward compat) ──────────────────────────────

@router.get("/pnl")
def bao_cao_pnl(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu: Optional[date_cls] = Query(None, alias="from"),
    den: Optional[date_cls] = Query(None, alias="to"),
    compare: int = Query(0, ge=0, le=1, description="1 → trả thêm previous + delta"),
):
    """Legacy P&L waterfall trong khoảng [from, to].

    `compare=1` → trả thêm `previous` (kỳ trước cùng độ dài) và `delta` so sánh.
    """
    tu, den = _resolve_range(tu, den)
    n_days = (den - tu).days + 1

    current = _build_pnl(db, tu, den)
    out: dict[str, Any] = {
        "ok": True,
        "from": str(tu),
        "to": str(den),
        "n_days": n_days,
        "current": current,
    }

    if compare == 1:
        prev_tu, prev_den = _previous_range(tu, den)
        previous = _build_pnl(db, prev_tu, prev_den)
        out["previous"] = previous
        out["delta"] = {
            "doanh_thu_abs": round(
                current["doanh_thu"]["total"] - previous["doanh_thu"]["total"], 2
            ),
            "doanh_thu_pct": _delta_pct(
                current["doanh_thu"]["total"], previous["doanh_thu"]["total"]
            ),
            "loi_nhuan_gop_abs": round(
                current["loi_nhuan_gop"] - previous["loi_nhuan_gop"], 2
            ),
            "loi_nhuan_gop_pct": _delta_pct(
                current["loi_nhuan_gop"], previous["loi_nhuan_gop"]
            ),
            "loi_nhuan_truoc_thue_abs": round(
                current["loi_nhuan_truoc_thue"] - previous["loi_nhuan_truoc_thue"], 2
            ),
            "loi_nhuan_truoc_thue_pct": _delta_pct(
                current["loi_nhuan_truoc_thue"], previous["loi_nhuan_truoc_thue"]
            ),
            "loi_nhuan_sau_thue_abs": round(
                current["loi_nhuan_sau_thue"] - previous["loi_nhuan_sau_thue"], 2
            ),
            "loi_nhuan_sau_thue_pct": _delta_pct(
                current["loi_nhuan_sau_thue"], previous["loi_nhuan_sau_thue"]
            ),
        }

    return out
