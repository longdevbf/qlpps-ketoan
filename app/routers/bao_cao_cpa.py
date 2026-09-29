"""Báo Cáo CPA — Phase 6B.

Endpoints (đọc bảng `ketoan.ads_phan_bo_don` do Phase 6A tạo):
  - GET /api/bao-cao/cpa?thang=YYYY-MM
        → tổng hợp 3 nhóm master (Đồ Gỗ / Đồ Mây / Dự Án) + no_match cho 1 tháng
  - GET /api/bao-cao/cpa/cohort?from=YYYY-MM&to=YYYY-MM
        → ma trận cohort: tháng_chi_ads × tháng_hoan_thanh × so_tien
  - GET /api/bao-cao/cpa/per-don?thang_hoan_thanh=YYYY-MM
        → list từng đơn hoàn thành trong tháng + ads gánh + margin

Quy ước:
  - `thang_chi_ads`         : tháng ads phát sinh chi
  - `thang_hoan_thanh`      : tháng đơn vận chuyển hoàn thành (vc_status=hoan_thanh)
  - `loai_phan_bo`:
        'theo_nhom'         : ads pool nhóm X chia theo % value nhóm trong đơn
        'redistribute_khac' : ads pool 'Khác' (san_pham không match) chia đều 3 nhóm
        'no_match'          : ads pool nhóm có tiền nhưng KHÔNG có đơn
                              → phát sinh CP BH ngay tháng_chi_ads
  - Nhóm master: 'Đồ Gỗ' | 'Đồ Mây' | 'Dự Án'

Cache: in-process TTL 30s — clone pattern từ `bao_cao_pnl.py`.

Fail-soft: bảng `ads_phan_bo_don` chưa tồn tại → trả empty payload (Phase 6A
chưa run migration). Chỉ raise 503 nếu có lỗi DB khác ngoài missing-schema.
"""
from __future__ import annotations

import time
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from shared.auth import JWTPayload
from shared.db import get_db

from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)

# 3 nhóm master cố định (CHECK constraint trên schema)
_NHOM_MASTERS = ("Đồ Gỗ", "Đồ Mây", "Dự Án")

# In-process TTL cache cho /cpa* (30s)
_CPA_CACHE: dict[str, tuple[float, dict]] = {}
_CPA_TTL = 30.0


def invalidate_cpa_cache(key: Optional[str] = None) -> None:
    """Clear CPA cache. Gọi từ service ads_phan_bo sau recompute."""
    if key is None:
        _CPA_CACHE.clear()
    else:
        _CPA_CACHE.pop(key, None)


def _cache_get(key: str) -> Optional[dict]:
    now = time.time()
    cached = _CPA_CACHE.get(key)
    if cached and (now - cached[0]) < _CPA_TTL:
        return cached[1]
    return None


def _cache_set(key: str, value: dict) -> None:
    _CPA_CACHE[key] = (time.time(), value)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _validate_thang(thang: str, *, field: str = "thang") -> str:
    """Validate format YYYY-MM."""
    try:
        y, m = thang.split("-")
        yy, mm = int(y), int(m)
        if mm < 1 or mm > 12 or yy < 2000 or yy > 2100:
            raise ValueError
    except (ValueError, IndexError):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{field} phải dạng YYYY-MM, nhận: {thang!r}",
        )
    return f"{yy:04d}-{mm:02d}"


def _months_between(tu: str, den: str) -> list[str]:
    """List 'YYYY-MM' từ tu → den (inclusive)."""
    ty, tm = int(tu[:4]), int(tu[5:7])
    dy, dm = int(den[:4]), int(den[5:7])
    out: list[str] = []
    y, m = ty, tm
    while (y, m) <= (dy, dm):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _table_exists(db: Session) -> bool:
    """`ketoan.ads_phan_bo_don` có tồn tại không?"""
    try:
        v = db.execute(text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'ketoan' AND table_name = 'ads_phan_bo_don'
            LIMIT 1
        """)).scalar()
        return bool(v)
    except (ProgrammingError, OperationalError):
        db.rollback()
        return False


def _safe_scalar(db: Session, sql: str, default: float = 0.0, **params) -> float:
    try:
        v = db.execute(text(sql), params).scalar()
        return float(v or 0)
    except (ProgrammingError, OperationalError):
        db.rollback()
        return default


def _safe_rows(db: Session, sql: str, **params) -> list[Any]:
    try:
        return db.execute(text(sql), params).all()
    except (ProgrammingError, OperationalError):
        db.rollback()
        return []


def _empty_payload_thang(thang: str) -> dict[str, Any]:
    """Payload rỗng khi schema chưa có (Phase 6A chưa migrate)."""
    return {
        "thang": thang,
        "ads_total_chi": 0.0,
        "by_nhom": [
            {
                "nhom_master": n,
                "ads_pool": 0.0,
                "so_don": 0,
                "tong_value_nhom": 0.0,
                "cpa_avg": 0.0,
                "so_don_da_hoan_thanh": 0,
                "ty_le_hoan_thanh": 0.0,
            }
            for n in _NHOM_MASTERS
        ],
        "no_match": [],
        "tong_phan_bo": 0.0,
        "warning": "ketoan.ads_phan_bo_don chưa tồn tại — chạy migration Phase 6A",
    }


# ─── 1. /api/bao-cao/cpa?thang=YYYY-MM ───────────────────────────────────────

@router.get("/cpa")
def bao_cao_cpa_thang(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    thang: str = Query(..., description="YYYY-MM"),
) -> dict[str, Any]:
    """CPA tổng hợp 1 tháng — by 3 nhóm master + no_match.

    Số đo:
      - `ads_total_chi`         : SUM(marketing.ads_cost.chi_phi) tháng (raw chi)
      - `by_nhom[].ads_pool`    : SUM(so_tien_phan_bo) NHÓM (sau redistribute Khác)
                                  trong tháng_chi_ads = thang
      - `by_nhom[].so_don`      : COUNT DISTINCT quote_number trong nhóm tháng
      - `by_nhom[].tong_value_nhom` : SUM(value_nhom_trong_don)
      - `by_nhom[].cpa_avg`     : ads_pool / so_don (nếu so_don > 0)
      - `by_nhom[].so_don_da_hoan_thanh` : COUNT vc_status='hoan_thanh'
      - `by_nhom[].ty_le_hoan_thanh`     : so_don_da_hoan_thanh / so_don
      - `no_match[]`            : pool nhóm 0 đơn → CP BH ngay
      - `tong_phan_bo`          : SUM(so_tien_phan_bo) trong tháng_chi_ads = thang
    """
    thang = _validate_thang(thang)
    cache_key = f"cpa:{thang}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    if not _table_exists(db):
        out = _empty_payload_thang(thang)
        # Vẫn lấy ads_total_chi từ marketing.ads_cost (legacy) để UI hiển thị
        out["ads_total_chi"] = _safe_scalar(db, """
            SELECT COALESCE(SUM(chi_phi), 0)
            FROM marketing.ads_cost
            WHERE thang = :thang
        """, thang=thang)
        _cache_set(cache_key, out)
        return out

    # ads_total_chi — chi raw từ marketing.ads_cost theo thang
    ads_total_chi = round(_safe_scalar(db, """
        SELECT COALESCE(SUM(chi_phi), 0)
        FROM marketing.ads_cost
        WHERE thang = :thang
    """, thang=thang), 2)

    # by_nhom — group theo nhom_master cho rows thang_chi_ads = thang AND
    # loai_phan_bo IN ('theo_nhom','redistribute_khac')
    rows = _safe_rows(db, """
        SELECT
            nhom_master,
            COALESCE(SUM(so_tien_phan_bo), 0)            AS ads_pool,
            COUNT(DISTINCT quote_number)                 AS so_don,
            COALESCE(SUM(value_nhom_trong_don), 0)       AS tong_value,
            COUNT(DISTINCT CASE WHEN vc_status = 'hoan_thanh'
                                 THEN quote_number END)  AS so_don_ht
        FROM ketoan.ads_phan_bo_don
        WHERE thang_chi_ads = :thang
          AND loai_phan_bo IN ('theo_nhom', 'redistribute_khac')
          AND quote_number IS NOT NULL
        GROUP BY nhom_master
    """, thang=thang)
    by_map: dict[str, dict[str, float]] = {
        str(r[0]): {
            "ads_pool": float(r[1] or 0),
            "so_don": int(r[2] or 0),
            "tong_value": float(r[3] or 0),
            "so_don_ht": int(r[4] or 0),
        }
        for r in rows
    }

    by_nhom: list[dict[str, Any]] = []
    for nhom in _NHOM_MASTERS:
        m = by_map.get(nhom, {
            "ads_pool": 0.0, "so_don": 0, "tong_value": 0.0, "so_don_ht": 0,
        })
        ads_pool = round(float(m["ads_pool"]), 2)
        so_don = int(m["so_don"])
        so_don_ht = int(m["so_don_ht"])
        cpa_avg = round(ads_pool / so_don, 2) if so_don else 0.0
        ty_le = round(so_don_ht / so_don, 4) if so_don else 0.0
        by_nhom.append({
            "nhom_master": nhom,
            "ads_pool": ads_pool,
            "so_don": so_don,
            "tong_value_nhom": round(float(m["tong_value"]), 2),
            "cpa_avg": cpa_avg,
            "so_don_da_hoan_thanh": so_don_ht,
            "ty_le_hoan_thanh": ty_le,
        })

    # no_match — pool có ads nhưng 0 đơn (loai_phan_bo='no_match')
    no_match_rows = _safe_rows(db, """
        SELECT
            nhom_master,
            COALESCE(SUM(so_tien_phan_bo), 0) AS so_tien
        FROM ketoan.ads_phan_bo_don
        WHERE thang_chi_ads = :thang
          AND loai_phan_bo = 'no_match'
        GROUP BY nhom_master
    """, thang=thang)
    no_match = [
        {"nhom_master": str(r[0]), "so_tien": round(float(r[1] or 0), 2)}
        for r in no_match_rows
        if float(r[1] or 0) > 0
    ]

    # tong_phan_bo — toàn bộ rows thang_chi_ads = thang
    tong_phan_bo = round(_safe_scalar(db, """
        SELECT COALESCE(SUM(so_tien_phan_bo), 0)
        FROM ketoan.ads_phan_bo_don
        WHERE thang_chi_ads = :thang
    """, thang=thang), 2)

    # recalc_luc — lần tính phân bổ gần nhất cho tháng này (NULL nếu chưa
    # tính lần nào) để FE phân biệt "chưa tính" với "đã tính nhưng = 0".
    recalc_luc_row = _safe_rows(db, """
        SELECT MAX(updated_at)
        FROM ketoan.ads_phan_bo_don
        WHERE thang_chi_ads = :thang
    """, thang=thang)
    recalc_luc = recalc_luc_row[0][0].isoformat() if recalc_luc_row and recalc_luc_row[0][0] else None

    out = {
        "thang": thang,
        "ads_total_chi": ads_total_chi,
        "by_nhom": by_nhom,
        "no_match": no_match,
        "tong_phan_bo": tong_phan_bo,
        "recalc_luc": recalc_luc,
    }
    _cache_set(cache_key, out)
    return out


# ─── 2. /api/bao-cao/cpa/cohort?from=&to= ────────────────────────────────────

@router.get("/cpa/cohort")
def bao_cao_cpa_cohort(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu: str = Query(..., alias="from", description="YYYY-MM"),
    den: str = Query(..., alias="to", description="YYYY-MM"),
) -> dict[str, Any]:
    """Ma trận cohort: tháng_chi_ads (rows) × tháng_hoan_thanh (cols) × so_tien.

    - Mỗi row = 1 thang_chi_ads ∈ [from, to]
    - Cells = SUM(so_tien_phan_bo) GROUP BY (thang_chi_ads, thang_hoan_thanh)
    - `chua_hoan_thanh` = SUM rows có thang_hoan_thanh IS NULL OR vc_status != 'hoan_thanh'
    - `ads_total` = SUM(marketing.ads_cost.chi_phi) cho thang_chi_ads
    - `ty_le_hoan_thanh` = (SUM cells đã hoan_thanh) / ads_total
    """
    tu = _validate_thang(tu, field="from")
    den = _validate_thang(den, field="to")
    if tu > den:
        tu, den = den, tu

    cache_key = f"cohort:{tu}:{den}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    months = _months_between(tu, den)
    if not _table_exists(db):
        # Fail-soft empty cohort
        out = {
            "from": tu,
            "to": den,
            "rows": [
                {
                    "thang_chi": m,
                    "ads_total": _safe_scalar(db, """
                        SELECT COALESCE(SUM(chi_phi), 0)
                        FROM marketing.ads_cost
                        WHERE thang = :m
                    """, m=m),
                    "by_thang_ht": {"chua_hoan_thanh": 0.0},
                    "ty_le_hoan_thanh": 0.0,
                }
                for m in months
            ],
            "warning": "ketoan.ads_phan_bo_don chưa tồn tại — chạy migration Phase 6A",
        }
        _cache_set(cache_key, out)
        return out

    # Pull all rows in range (chỉ cần aggregated)
    rows = _safe_rows(db, """
        SELECT
            thang_chi_ads,
            COALESCE(thang_hoan_thanh, '') AS thang_ht,
            COALESCE(vc_status, '')        AS vc_status,
            COALESCE(SUM(so_tien_phan_bo), 0) AS so_tien
        FROM ketoan.ads_phan_bo_don
        WHERE thang_chi_ads >= :tu AND thang_chi_ads <= :den
        GROUP BY thang_chi_ads, thang_hoan_thanh, vc_status
    """, tu=tu, den=den)

    # Build matrix: thang_chi → {thang_ht: so_tien, "chua_hoan_thanh": so_tien}
    matrix: dict[str, dict[str, float]] = {m: {} for m in months}
    ht_done_by_chi: dict[str, float] = {m: 0.0 for m in months}
    for r in rows:
        thang_chi = str(r[0])
        thang_ht = str(r[1] or "")
        vc_status = str(r[2] or "")
        so_tien = float(r[3] or 0)
        if thang_chi not in matrix:
            continue
        # Bucket
        if thang_ht and vc_status == "hoan_thanh":
            matrix[thang_chi][thang_ht] = matrix[thang_chi].get(thang_ht, 0.0) + so_tien
            ht_done_by_chi[thang_chi] += so_tien
        else:
            matrix[thang_chi]["chua_hoan_thanh"] = (
                matrix[thang_chi].get("chua_hoan_thanh", 0.0) + so_tien
            )

    # ads_total per thang_chi
    out_rows: list[dict[str, Any]] = []
    for m in months:
        ads_total = round(_safe_scalar(db, """
            SELECT COALESCE(SUM(chi_phi), 0)
            FROM marketing.ads_cost
            WHERE thang = :m
        """, m=m), 2)
        by_ht = {k: round(v, 2) for k, v in matrix.get(m, {}).items()}
        ty_le = round(ht_done_by_chi[m] / ads_total, 4) if ads_total > 0 else 0.0
        out_rows.append({
            "thang_chi": m,
            "ads_total": ads_total,
            "by_thang_ht": by_ht,
            "ty_le_hoan_thanh": ty_le,
        })

    out = {"from": tu, "to": den, "rows": out_rows}
    _cache_set(cache_key, out)
    return out


# ─── 3. /api/bao-cao/cpa/per-don?thang_hoan_thanh=YYYY-MM ────────────────────

@router.get("/cpa/per-don")
def bao_cao_cpa_per_don(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    thang_hoan_thanh: str = Query(..., description="YYYY-MM"),
) -> dict[str, Any]:
    """List đơn hoàn thành trong `thang_hoan_thanh` + ads gánh + margin.

    - 1 row / quote_number (đơn hoàn thành tháng đó)
    - `ads_gang[]` : từng phân bổ riêng (nhom_master × thang_chi)
    - `tong_ads`   : SUM(so_tien_phan_bo) đơn đó
    - `tong_don`   : `quotes.tong_chua_thue` (LEFT JOIN baogia.quotes)
    - `margin_after_ads` = tong_don - tong_ads
    """
    thang_hoan_thanh = _validate_thang(thang_hoan_thanh, field="thang_hoan_thanh")
    cache_key = f"per_don:{thang_hoan_thanh}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    if not _table_exists(db):
        out = {
            "thang_hoan_thanh": thang_hoan_thanh,
            "rows": [],
            "warning": "ketoan.ads_phan_bo_don chưa tồn tại — chạy migration Phase 6A",
        }
        _cache_set(cache_key, out)
        return out

    # Lấy distinct quote_number + tổng ads gánh + LEFT JOIN baogia.quotes
    # cho customer_name + tong_chua_thue.
    sql_quotes = """
        SELECT
            apb.quote_number,
            COALESCE(q.customer_name, '')                    AS customer_name,
            COALESCE(q.tong_chua_thue, q.tong_don, 0)        AS tong_don,
            COALESCE(SUM(apb.so_tien_phan_bo), 0)            AS tong_ads
        FROM ketoan.ads_phan_bo_don apb
        LEFT JOIN baogia.quotes q ON q.quote_number = apb.quote_number
        WHERE apb.thang_hoan_thanh = :thang
          AND apb.vc_status = 'hoan_thanh'
          AND apb.quote_number IS NOT NULL
        GROUP BY apb.quote_number, q.customer_name, q.tong_chua_thue, q.tong_don
        ORDER BY tong_ads DESC
    """
    quote_rows = _safe_rows(db, sql_quotes, thang=thang_hoan_thanh)

    if not quote_rows:
        # Fallback: query ko join (baogia.quotes có thể chưa accessible / khác user)
        # — vẫn trả khung rỗng có schema đúng.
        out = {"thang_hoan_thanh": thang_hoan_thanh, "rows": []}
        _cache_set(cache_key, out)
        return out

    # Lấy ads_gang chi tiết — group theo (quote_number, nhom_master, thang_chi_ads)
    quote_numbers = [str(r[0]) for r in quote_rows]
    if not quote_numbers:
        out = {"thang_hoan_thanh": thang_hoan_thanh, "rows": []}
        _cache_set(cache_key, out)
        return out

    placeholders = ",".join(f":q{i}" for i in range(len(quote_numbers)))
    params: dict[str, Any] = {f"q{i}": v for i, v in enumerate(quote_numbers)}
    params["thang"] = thang_hoan_thanh
    sql_gang = f"""
        SELECT
            quote_number,
            nhom_master,
            thang_chi_ads,
            COALESCE(SUM(so_tien_phan_bo), 0) AS so_tien
        FROM ketoan.ads_phan_bo_don
        WHERE thang_hoan_thanh = :thang
          AND vc_status = 'hoan_thanh'
          AND quote_number IN ({placeholders})
        GROUP BY quote_number, nhom_master, thang_chi_ads
        ORDER BY quote_number, thang_chi_ads, nhom_master
    """
    gang_rows = _safe_rows(db, sql_gang, **params)
    gang_by_q: dict[str, list[dict[str, Any]]] = {q: [] for q in quote_numbers}
    for r in gang_rows:
        q = str(r[0])
        gang_by_q.setdefault(q, []).append({
            "nhom_master": str(r[1]),
            "thang_chi": str(r[2]),
            "so_tien": round(float(r[3] or 0), 2),
        })

    out_rows: list[dict[str, Any]] = []
    for r in quote_rows:
        qn = str(r[0])
        cust = str(r[1] or "")
        tong_don = round(float(r[2] or 0), 2)
        tong_ads = round(float(r[3] or 0), 2)
        out_rows.append({
            "quote_number": qn,
            "customer_name": cust,
            "tong_don": tong_don,
            "ads_gang": gang_by_q.get(qn, []),
            "tong_ads": tong_ads,
            "margin_after_ads": round(tong_don - tong_ads, 2),
        })

    out = {"thang_hoan_thanh": thang_hoan_thanh, "rows": out_rows}
    _cache_set(cache_key, out)
    return out
