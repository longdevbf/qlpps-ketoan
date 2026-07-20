"""Phân bổ chi phí ads tháng X vào từng đơn báo giá đã chốt — Phase 6A.

Quy tắc đã chốt với chị Trang:
    1. 3 nhóm cố định: 'Đồ Gỗ' | 'Đồ Mây' | 'Dự Án' (không có nhóm 4).
    2. Ads "Khác" (san_pham không match 3 nhóm) chia đều 3 nhóm
       (tổng ads không đổi).
    3. Phân bổ trong pool nhóm: theo % giá trị nhóm trong từng đơn so với
       tổng giá trị nhóm đó của tất cả đơn chốt T X.

Matching principle:
    - thang_chi_ads = T X (tháng marketing chi tiền ads)
    - đơn chốt T X = quote.duyet_status='approved' AND duyet_luc trong T X
    - khi VC `hoan_thanh` → row được flag thang_hoan_thanh = T thực hoàn
      thành → CP BH tháng đó (PL calculator phía Agent 6B sẽ tổng hợp).

Service expose:
    recalc_ads_phan_bo(db, thang) -> dict      # Tính lại + ghi DB
    get_pool_breakdown(db, thang) -> dict      # Read summary
    sync_vc_status_for_quote(db, ma_don, vc_status, thang_ht=None)
                                               # Hook cho external.py
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date as date_cls
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


# ────────────────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────────────────

NHOM_MASTERS = ("Đồ Gỗ", "Đồ Mây", "Dự Án")


# ────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────

def _to_float(x: Any) -> float:
    """Convert Decimal/None/str → float, fail-soft → 0."""
    if x is None:
        return 0.0
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _round2(x: float) -> float:
    """Round to 2 decimal places (HALF_UP)."""
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _lookup_nhom_master_for_san_pham(
    db: Session, san_pham_text: Optional[str]
) -> Optional[str]:
    """Resolve nhom_master cho 1 chuỗi san_pham (từ ads_cost.san_pham hoặc
    quote_items.product_name) qua shared.products.

    Strategy:
      1. exact match `ten_sp = san_pham_text` (case-insensitive).
      2. fallback ILIKE: `ten_sp ILIKE %san_pham_text%` HOẶC ngược lại.
      3. Nếu không match → return None (nghĩa là "Khác").

    Chỉ trả nhóm nếu products.nhom_master IN 3 nhóm hợp lệ.
    """
    if not san_pham_text:
        return None
    s = san_pham_text.strip()
    if not s:
        return None

    # 1. Exact case-insensitive
    row = db.execute(
        text("""
            SELECT nhom_master FROM shared.products
            WHERE LOWER(ten_sp) = LOWER(:s)
              AND nhom_master IS NOT NULL
            LIMIT 1
        """),
        {"s": s},
    ).first()
    if row and row[0] in NHOM_MASTERS:
        return row[0]

    # 2. ILIKE 2-way (sp text in product, or product in sp text)
    row = db.execute(
        text("""
            SELECT nhom_master, ten_sp FROM shared.products
            WHERE nhom_master IS NOT NULL
              AND (ten_sp ILIKE :pat OR :s ILIKE '%' || ten_sp || '%')
            ORDER BY LENGTH(ten_sp) DESC
            LIMIT 1
        """),
        {"s": s, "pat": f"%{s}%"},
    ).first()
    if row and row[0] in NHOM_MASTERS:
        return row[0]

    return None


def _get_quote_nhom_breakdown(
    db: Session, quote_id: int, fallback_total: float = 0.0
) -> dict[str, float]:
    """Trả {nhom_master: SUM(line_value)} cho 1 quote.

    line_value = so_luong * COALESCE(don_gia_tinh, don_gia_goc)
                  (fallback thanh_tien nếu cả 2 NULL).

    Chỉ count items match 1 trong 3 nhóm. Items "Khác" bị bỏ qua
    (không tham gia phân bổ — không nhận pool).

    Edge case: nếu 0 item match nhóm nào (đơn full Khác) → trả {}.
    """
    rows = db.execute(
        text("""
            SELECT
                qi.id,
                qi.product_name,
                qi.so_luong,
                qi.don_gia_tinh,
                qi.don_gia_goc,
                qi.thanh_tien
            FROM baogia.quote_items qi
            WHERE qi.quote_id = :qid
              AND COALESCE(qi.product_name, '') != ''
        """),
        {"qid": quote_id},
    ).mappings().all()

    breakdown: dict[str, float] = defaultdict(float)
    for r in rows:
        nhom = _lookup_nhom_master_for_san_pham(db, r["product_name"])
        if nhom is None:
            continue
        sl = _to_float(r["so_luong"]) or 1.0
        dg = _to_float(r["don_gia_tinh"]) or _to_float(r["don_gia_goc"])
        line_val = sl * dg
        if line_val <= 0:
            line_val = _to_float(r["thanh_tien"])
        if line_val > 0:
            breakdown[nhom] += line_val

    return dict(breakdown)


def _invalidate_pl_cache(thang: str) -> None:
    """Clear PL cache để tháng X được tính lại lần kế."""
    try:
        # Late import tránh circular
        from ..routers.bao_cao_pnl import invalidate_pl_cache
        invalidate_pl_cache()
    except Exception:
        pass


# ────────────────────────────────────────────────────────────────────────
# Main: recalc_ads_phan_bo
# ────────────────────────────────────────────────────────────────────────

def recalc_ads_phan_bo(db: Session, thang: str) -> dict[str, Any]:
    """Recalc full bảng phân bổ ads cho tháng X.

    Args:
        db: SQLAlchemy session (caller responsible for commit/rollback).
        thang: 'YYYY-MM'.

    Returns:
        dict — xem `AdsPhanBoSummary` schema. Bao gồm:
            ads_total, ads_by_nhom, ads_unmatched,
            pool_after_redistribute, n_quotes_chot, rows_inserted,
            no_match_pools.

    Side effects:
        - DELETE FROM ketoan.ads_phan_bo_don WHERE thang_chi_ads = :thang
        - INSERT các dòng phân bổ mới
        - Invalidate PL cache
    """
    if not thang or len(thang) != 7 or thang[4] != "-":
        raise ValueError(f"thang phải là 'YYYY-MM', got {thang!r}")

    # ───── BƯỚC 1: Group ads theo nhóm ─────────────────────────────────
    ads_rows = db.execute(
        text("""
            SELECT id, san_pham, COALESCE(chi_phi, 0) AS chi_phi
            FROM marketing.ads_cost
            WHERE thang = :thang
        """),
        {"thang": thang},
    ).mappings().all()

    ads_by_nhom: dict[str, float] = {n: 0.0 for n in NHOM_MASTERS}
    ads_unmatched: float = 0.0

    for r in ads_rows:
        chi_phi = _to_float(r["chi_phi"])
        if chi_phi <= 0:
            continue
        nhom = _lookup_nhom_master_for_san_pham(db, r["san_pham"])
        if nhom in NHOM_MASTERS:
            ads_by_nhom[nhom] += chi_phi
        else:
            ads_unmatched += chi_phi

    ads_total = sum(ads_by_nhom.values()) + ads_unmatched

    # ───── BƯỚC 3 (move up): List quotes chốt T X ────────────────────
    # Cần biết nhóm nào có đơn TRƯỚC khi redistribute Khác
    quote_rows = db.execute(
        text("""
            SELECT q.id, q.quote_number, q.duyet_luc,
                   COALESCE(q.tong_chua_thue, 0) AS tong_chua_thue
            FROM baogia.quotes q
            WHERE TO_CHAR(q.duyet_luc, 'YYYY-MM') = :thang
              AND q.duyet_status = 'approved'
              AND q.quote_number IS NOT NULL
        """),
        {"thang": thang},
    ).mappings().all()

    n_quotes_chot = len(quote_rows)

    # ───── BƯỚC 4: Breakdown từng quote theo nhóm ─────────────────────
    quote_groups: dict[int, dict[str, Any]] = {}
    for q in quote_rows:
        qid = q["id"]
        groups = _get_quote_nhom_breakdown(db, qid)
        if not groups:
            continue
        ngay_chot = q["duyet_luc"]
        if ngay_chot is not None and not isinstance(ngay_chot, date_cls):
            try:
                ngay_chot = ngay_chot.date()
            except Exception:
                ngay_chot = None
        quote_groups[qid] = {
            "quote_number": q["quote_number"],
            "ngay_chot": ngay_chot,
            "groups": groups,
        }

    # ───── BƯỚC 2 (sau khi đã có quote_groups): Redistribute thông minh
    # Quy tắc mới (anh chốt):
    #   - Nhóm có đơn      → giữ ads gốc của nhóm
    #   - Nhóm KHÔNG có đơn → ads của nhóm đó CHUYỂN sang "Khác"
    #   - "Khác" (gốc + ads-không-có-đơn-nào-trong-nhóm) → chia ĐỀU CHO CÁC NHÓM CÓ ĐƠN
    #   - Nếu KHÔNG nhóm nào có đơn → toàn bộ ads ghi 'no_match' tháng X
    nhom_co_don: set[str] = set()
    for qmeta in quote_groups.values():
        for nhom in qmeta["groups"].keys():
            nhom_co_don.add(nhom)

    # Đẩy ads của nhóm KHÔNG có đơn vào pot Khác
    for n in NHOM_MASTERS:
        if n not in nhom_co_don and ads_by_nhom[n] > 0:
            ads_unmatched += ads_by_nhom[n]
            ads_by_nhom[n] = 0.0

    # Redistribute Khác chỉ chia cho nhóm CÓ đơn
    if nhom_co_don and ads_unmatched > 0:
        khac_share = ads_unmatched / len(nhom_co_don)
    else:
        khac_share = 0.0

    pool: dict[str, float] = {}
    for n in NHOM_MASTERS:
        if n in nhom_co_don:
            pool[n] = ads_by_nhom[n] + khac_share
        else:
            # Nhóm không có đơn → pool=0 (ads đã chuyển vào Khác)
            # Nhưng nếu nhóm khác cũng không có đơn → giữ no_match phần ads còn lại
            pool[n] = 0.0

    # Edge case: 0 nhóm có đơn → ads_unmatched chưa được tiêu thụ
    # → Ghi 'no_match' theo nhóm gốc đã group ở bước 1 (đã reset = 0 lúc trên)
    # → Phải khôi phục lại để có thông tin no_match
    if not nhom_co_don and ads_total > 0:
        # Toàn bộ ads thành no_match — phân bổ ngược cho 3 nhóm để track
        no_match_per_nhom = ads_total / 3.0
        for n in NHOM_MASTERS:
            pool[n] = no_match_per_nhom

    # ───── BƯỚC 5: Phân bổ — DELETE + INSERT ──────────────────────────
    db.execute(
        text("""
            DELETE FROM ketoan.ads_phan_bo_don
            WHERE thang_chi_ads = :thang
        """),
        {"thang": thang},
    )

    rows_inserted = 0
    no_match_pools: list[dict] = []

    for nhom, P in pool.items():
        if P <= 0:
            continue

        # Eligible: list (quote_meta, value_nhom_trong_don)
        eligible = [
            (qmeta, qmeta["groups"][nhom])
            for qmeta in quote_groups.values()
            if nhom in qmeta["groups"] and qmeta["groups"][nhom] > 0
        ]

        if not eligible:
            # Pool có ads nhưng không có đơn match → no_match
            db.execute(
                text("""
                    INSERT INTO ketoan.ads_phan_bo_don
                      (thang_chi_ads, nhom_master, quote_number, ngay_chot,
                       value_nhom_trong_don, ty_le_pool, so_tien_phan_bo,
                       loai_phan_bo, vc_status, thang_hoan_thanh,
                       cpa_nhom_snapshot)
                    VALUES
                      (:thang, :nhom, NULL, NULL, NULL, NULL, :st,
                       'no_match', NULL, NULL, NULL)
                """),
                {"thang": thang, "nhom": nhom, "st": _round2(P)},
            )
            rows_inserted += 1
            no_match_pools.append({"nhom": nhom, "so_tien": _round2(P)})
            continue

        # Tổng giá trị nhóm trong tất cả đơn eligible
        total_val = sum(v for _, v in eligible) or 1e-9

        # CPA snapshot = pool / số đơn match
        cpa_snap = _round2(P / len(eligible))

        # Có ads từ pool Khác chia vào nhóm này không?
        has_redistribute = ads_unmatched > 0
        # Loại phân bổ:
        # - 'theo_nhom' khi pool = ads_by_nhom (no Khác)
        # - 'redistribute_khac' khi nhóm chỉ có ads từ Khác (ads_by_nhom[nhom]=0)
        # - 'theo_nhom' khi nhóm có cả 2 (mix) — rút gọn
        if ads_by_nhom[nhom] == 0 and has_redistribute:
            loai = "redistribute_khac"
        else:
            loai = "theo_nhom"

        for qmeta, val in eligible:
            ty_le = val / total_val
            so_tien = _round2(P * ty_le)
            db.execute(
                text("""
                    INSERT INTO ketoan.ads_phan_bo_don
                      (thang_chi_ads, nhom_master, quote_number, ngay_chot,
                       value_nhom_trong_don, ty_le_pool, so_tien_phan_bo,
                       loai_phan_bo, vc_status, thang_hoan_thanh,
                       cpa_nhom_snapshot)
                    VALUES
                      (:thang, :nhom, :qn, :nc, :val, :tl, :st,
                       :loai, NULL, NULL, :cpa)
                """),
                {
                    "thang": thang,
                    "nhom": nhom,
                    "qn": qmeta["quote_number"],
                    "nc": qmeta["ngay_chot"],
                    "val": _round2(val),
                    "tl": round(ty_le, 4),
                    "st": so_tien,
                    "loai": loai,
                    "cpa": cpa_snap,
                },
            )
            rows_inserted += 1

    # ───── BƯỚC 6: Sync vc_status cho rows mới insert ────────────────
    # Một đơn có thể đã hoan_thanh trước khi recalc → cập nhật vc_status
    # ngay để PL calculator phía Agent 6B đọc đúng.
    db.execute(
        text("""
            UPDATE ketoan.ads_phan_bo_don apb
            SET vc_status = v.trang_thai,
                thang_hoan_thanh = CASE
                    WHEN v.trang_thai = 'hoan_thanh'
                      THEN TO_CHAR(COALESCE(v.updated_at, NOW()), 'YYYY-MM')
                    ELSE NULL END,
                updated_at = NOW()
            FROM saleadmin.vanchuyen v
            WHERE apb.thang_chi_ads = :thang
              AND apb.quote_number IS NOT NULL
              AND v.ma_don = apb.quote_number
        """),
        {"thang": thang},
    )

    # ───── BƯỚC 7: Invalidate cache + return summary ─────────────────
    _invalidate_pl_cache(thang)

    return {
        "thang": thang,
        "ads_total": _round2(ads_total),
        "ads_by_nhom": {k: _round2(v) for k, v in ads_by_nhom.items()},
        "ads_unmatched": _round2(ads_unmatched),
        "pool_after_redistribute": {k: _round2(v) for k, v in pool.items()},
        "n_quotes_chot": n_quotes_chot,
        "rows_inserted": rows_inserted,
        "no_match_pools": no_match_pools,
    }


# ────────────────────────────────────────────────────────────────────────
# Read helpers (cho /summary endpoint)
# ────────────────────────────────────────────────────────────────────────

def get_pool_breakdown(db: Session, thang: str) -> dict[str, Any]:
    """Đọc lại summary từ DB cho 1 tháng (không recalc).

    Khác recalc_ads_phan_bo: chỉ aggregate dữ liệu hiện tại trong
    `ads_phan_bo_don` thay vì tính lại từ marketing.ads_cost.
    Dùng khi UI muốn refresh nhanh.
    """
    rows = db.execute(
        text("""
            SELECT nhom_master,
                   SUM(so_tien_phan_bo)::float AS pool_total,
                   COUNT(*) FILTER (WHERE quote_number IS NOT NULL)::int AS n_quotes,
                   COUNT(*) FILTER (WHERE loai_phan_bo = 'no_match')::int AS n_no_match,
                   SUM(so_tien_phan_bo) FILTER (
                       WHERE loai_phan_bo = 'no_match'
                   )::float AS no_match_total
            FROM ketoan.ads_phan_bo_don
            WHERE thang_chi_ads = :thang
            GROUP BY nhom_master
        """),
        {"thang": thang},
    ).mappings().all()

    pool: dict[str, float] = {n: 0.0 for n in NHOM_MASTERS}
    n_quotes_total = 0
    no_match_pools: list[dict] = []
    for r in rows:
        n = r["nhom_master"]
        if n in pool:
            pool[n] = _round2(_to_float(r["pool_total"]))
        n_quotes_total += int(r["n_quotes"] or 0)
        if r["n_no_match"]:
            no_match_pools.append({
                "nhom": n,
                "so_tien": _round2(_to_float(r["no_match_total"])),
            })

    total = sum(pool.values())

    return {
        "thang": thang,
        "ads_total": _round2(total),
        "ads_by_nhom": {},  # không tính lại — UI nên gọi recalc nếu cần
        "ads_unmatched": 0.0,
        "pool_after_redistribute": pool,
        "n_quotes_chot": n_quotes_total,
        "rows_inserted": 0,
        "no_match_pools": no_match_pools,
    }


def sync_vc_status_for_quote(
    db: Session,
    ma_don: str,
    vc_status: str,
    thang_hoan_thanh: Optional[str] = None,
) -> int:
    """Update vc_status + thang_hoan_thanh cho mọi rows ads_phan_bo_don
    có quote_number = ma_don.

    Gọi từ external.mark_vanchuyen_completed sau khi VC chuyển 'hoan_thanh'.

    Returns: số dòng updated.
    """
    if not ma_don:
        return 0

    res = db.execute(
        text("""
            UPDATE ketoan.ads_phan_bo_don
            SET vc_status = :st,
                thang_hoan_thanh = :tht,
                updated_at = NOW()
            WHERE quote_number = :mn
        """),
        {"st": vc_status, "tht": thang_hoan_thanh, "mn": ma_don},
    )

    # Invalidate PL cache (nếu đã có thang_ht)
    if thang_hoan_thanh:
        _invalidate_pl_cache(thang_hoan_thanh)

    return res.rowcount or 0
