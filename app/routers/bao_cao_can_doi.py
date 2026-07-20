"""Báo Cáo Cân Đối Tài Chính (Balance Sheet) — refactor M5.

Endpoint:
    GET /api/bao-cao/can-doi?thang=YYYY-MM

Hai vế:
  TÀI SẢN
    1. Tiền & tương đương: tk_ngan_hang (M4 tai_khoan_nh_giao_dich) + tien_mat_so_quy
    2. Phải thu KH (cong_no loai='phai_thu', còn lại)
    3. Hàng tồn kho (M1 inventory_balance.gia_tri_ton)
    4. TSCĐ ròng (phase 2 — 0)
  NGUỒN VỐN
    1. Nợ phải trả: phai_tra_ncc + vay_ngan_han + vay_dai_han + phai_tra_nv (phase 2 = 0)
    2. Vốn chủ sở hữu: von_gop + ln_giu_lai + quy_dn

Cross-app reads (M1/M4 bảng có thể chưa migrate) dùng raw SQL `text()` fail-soft.
"""
from calendar import monthrange
from datetime import date as date_cls
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

from shared.auth import JWTPayload
from shared.db import get_db

from ..models import CongNo, KyKeToan
from ..services.journal import get_balance_sheet_aggregates
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


# ─── helpers ─────────────────────────────────────────────────────────────────

def _f(v: Any) -> float:
    return float(v or 0)


def _safe_scalar(db: Session, sql: str, default: float = 0.0, **params) -> float:
    try:
        v = db.execute(text(sql), params).scalar()
        return float(v or 0)
    except (ProgrammingError, OperationalError):
        db.rollback()
        return float(default)


def _safe_rows(db: Session, sql: str, **params) -> list:
    try:
        return db.execute(text(sql), params).all()
    except (ProgrammingError, OperationalError):
        db.rollback()
        return []


def _resolve_thang(thang: Optional[str]) -> tuple[str, date_cls, date_cls]:
    """thang 'YYYY-MM' → (thang, tu, den)."""
    if not thang:
        today = date_cls.today()
        thang = today.strftime("%Y-%m")
    import re
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", thang):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"thang phải dạng YYYY-MM, nhận: {thang!r}",
        )
    yr, mo = int(thang[:4]), int(thang[5:7])
    tu = date_cls(yr, mo, 1)
    den = date_cls(yr, mo, monthrange(yr, mo)[1])
    return thang, tu, den


# ─── TÀI SẢN ─────────────────────────────────────────────────────────────────

def _balance_by_loai(db: Session, on_date: date_cls, loai: str) -> float:
    """Số dư cuối ngày `on_date` của tất cả TK theo `loai` (ngan_hang/tien_mat).

    Cùng logic với `/api/so-quy/summary` per-account → chốt 1 source of truth:
        per_TK_balance = COALESCE(SoDuDauKy của tháng on_date, so_du_dau ban đầu)
                       + Σ SoQuy(thu - chi) trong khoảng (đầu_tháng .. on_date)
        Trường hợp KHÔNG có SoDuDauKy của tháng đó → cộng dồn TẤT CẢ SoQuy
        từ trước cho tới on_date.

    Tổng = Σ per_TK. KHÔNG cộng `tai_khoan_nh_giao_dich` (M4) vì M4 mirror
    SoQuy → double-count làm số dư phồng lên gấp đôi (root cause user
    report 2026-05-07: tk_ngan_hang ở Cân Đối ≠ tổng TK NH page).
    """
    sm = date_cls(on_date.year, on_date.month, 1)
    rows = _safe_rows(
        db,
        """
        SELECT id, ten_tk, COALESCE(so_du_dau, 0) AS so_du_dau
        FROM ketoan.tai_khoan_nh
        WHERE COALESCE(active, true) = true AND loai = :loai
        """,
        loai=loai,
    )
    total = 0.0
    for tk_id, ten_tk, so_du_dau_init in rows:
        # 1. Số dư đầu tháng on_date — ưu tiên SoDuDauKy nếu có
        sddk = _safe_scalar(
            db,
            """
            SELECT so_du::float FROM ketoan.so_du_dau_ky
            WHERE tai_khoan_id = :tk_id AND thang = :sm
            """,
            tk_id=tk_id, sm=sm,
        )
        if sddk:
            so_du_dau_thang = float(sddk)
        else:
            # Fallback: so_du_dau ban đầu + Σ SoQuy(thu - chi) trước tháng
            net_truoc = _safe_scalar(
                db,
                """
                SELECT COALESCE(SUM(
                    CASE WHEN loai='thu' THEN so_tien
                         WHEN loai='chi' THEN -so_tien ELSE 0 END
                ), 0)::float
                FROM ketoan.so_quy
                WHERE tai_khoan = :ten_tk AND ngay < :sm
                """,
                ten_tk=ten_tk, sm=sm,
            )
            so_du_dau_thang = float(so_du_dau_init or 0) + float(net_truoc)

        # 2. Net flow trong tháng tới on_date (inclusive)
        net_in_month = _safe_scalar(
            db,
            """
            SELECT COALESCE(SUM(
                CASE WHEN loai='thu' THEN so_tien
                     WHEN loai='chi' THEN -so_tien ELSE 0 END
            ), 0)::float
            FROM ketoan.so_quy
            WHERE tai_khoan = :ten_tk AND ngay >= :sm AND ngay <= :on_date
            """,
            ten_tk=ten_tk, sm=sm, on_date=on_date,
        )
        total += so_du_dau_thang + float(net_in_month)
    return total


def _tk_ngan_hang_net(db: Session, on_date: date_cls) -> float:
    """Tổng số dư mọi TK loại='ngan_hang' tại on_date — match Tài Khoản NH page."""
    return _balance_by_loai(db, on_date, "ngan_hang")


def _tien_mat_so_quy_net(db: Session, on_date: date_cls) -> float:
    """Tổng số dư mọi TK loại='tien_mat' tại on_date — match Tài Khoản NH page."""
    return _balance_by_loai(db, on_date, "tien_mat")


def _phai_thu(db: Session, on_date: date_cls) -> float:
    """SUM(con_lai) cong_no loai='phai_thu' AND ngay <= on_date AND chưa trả hết."""
    rows = db.execute(
        select(func.coalesce(func.sum(CongNo.con_lai), 0))
        .where(CongNo.loai == "phai_thu")
        .where(CongNo.ngay <= on_date)
        .where(CongNo.trang_thai != "da_tra")
    ).scalar()
    return _f(rows)


def _hang_ton_kho(db: Session) -> float:
    """SUM(inventory_balance.gia_tri_ton) — M1 fail-soft."""
    sql = """
        SELECT COALESCE(SUM(gia_tri_ton), 0)::float
        FROM ketoan.inventory_balance
    """
    return _safe_scalar(db, sql)


def _tscd_breakdown(db: Session, on_date: date_cls) -> tuple[float, float]:
    """Phase 3 — TSCĐ ròng từ bảng `tai_san_co_dinh` (legacy fail-soft).

    Returns (nguyen_gia, hao_mon) — tscd_rong = nguyen_gia - hao_mon.
    Chỉ tính các TSCĐ trang_thai='dang_su_dung' và đã đi vào sử dụng
    (ngay_su_dung <= on_date).
    """
    nguyen_gia = _safe_scalar(
        db,
        """
        SELECT COALESCE(SUM(nguyen_gia), 0)::float
        FROM ketoan.tai_san_co_dinh
        WHERE trang_thai = 'dang_su_dung' AND ngay_su_dung <= :on_date
        """,
        on_date=on_date,
    )
    hao_mon = _safe_scalar(
        db,
        """
        SELECT COALESCE(SUM(hao_mon_luy_ke), 0)::float
        FROM ketoan.tai_san_co_dinh
        WHERE trang_thai = 'dang_su_dung' AND ngay_su_dung <= :on_date
        """,
        on_date=on_date,
    )
    return nguyen_gia, hao_mon


# ─── NGUỒN VỐN ───────────────────────────────────────────────────────────────

def _phai_tra_ncc(db: Session, on_date: date_cls) -> float:
    rows = db.execute(
        select(func.coalesce(func.sum(CongNo.con_lai), 0))
        .where(CongNo.loai == "phai_tra")
        .where(CongNo.ngay <= on_date)
        .where(CongNo.trang_thai != "da_tra")
    ).scalar()
    return _f(rows)


def _vay_ngan_han_dai_han(db: Session, on_date: date_cls) -> tuple[float, float]:
    """Phân loại vay: ky_han_thang <=12 → ngắn hạn; >12 → dài hạn.

    Dư nợ gốc = so_tien_vay - SUM(tra_goc + tra_goc_lai.so_tien_goc) đến on_date.
    """
    sql = """
        SELECT
            kv.id,
            kv.ky_han_thang,
            kv.so_tien_vay::float AS goc,
            COALESCE((
                SELECT SUM(
                    CASE
                        WHEN gd.loai = 'tra_goc' THEN gd.so_tien
                        WHEN gd.loai = 'tra_goc_lai' THEN COALESCE(gd.so_tien_goc, 0)
                        ELSE 0
                    END
                )
                FROM ketoan.khoan_vay_giao_dich gd
                WHERE gd.khoan_vay_id = kv.id AND gd.ngay <= :on_date
            ), 0)::float AS da_tra
        FROM ketoan.khoan_vay kv
        WHERE kv.ngay_vay <= :on_date AND kv.status = 'dang_vay'
    """
    rows = _safe_rows(db, sql, on_date=on_date)
    nh = 0.0
    dh = 0.0
    for _id, ky_han, goc, da_tra in rows:
        con_lai = max(0.0, _f(goc) - _f(da_tra))
        if int(ky_han or 0) <= 12:
            nh += con_lai
        else:
            dh += con_lai
    return nh, dh


def _von_gop(db: Session, on_date: date_cls) -> float:
    """SUM(von_chu_so_huu.so_tien) loai='gop_von' - loai='rut_von' (M4 fail-soft)."""
    sql = """
        SELECT COALESCE(SUM(
            CASE WHEN loai_giao_dich='gop_von' THEN so_tien
                 WHEN loai_giao_dich='rut_von' THEN -so_tien
                 ELSE 0 END
        ), 0)::float
        FROM ketoan.von_chu_so_huu
        WHERE ngay <= :on_date
    """
    return _safe_scalar(db, sql, on_date=on_date)


def _ln_giu_lai(db: Session, thang: str) -> float:
    """LN giữ lại tới `thang`:
       Lấy ky_ke_toan có thang <= `thang` và trang_thai='da_chot' MỚI NHẤT,
       trả ln_giu_lai_cuoi_ky của kỳ đó.
       LNST các tháng đã chốt SAU đó cũng cộng — nhưng theo logic kỳ trước
       phải chốt trước nên kỳ chốt mới nhất ≤ `thang` là đủ.
    """
    row = db.execute(
        select(KyKeToan)
        .where(KyKeToan.trang_thai == "da_chot")
        .where(KyKeToan.thang <= thang)
        .order_by(KyKeToan.thang.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None or row.ln_giu_lai_cuoi_ky is None:
        return 0.0
    return float(row.ln_giu_lai_cuoi_ky)


def _quy_dn_tong(db: Session) -> float:
    """SUM(quy_dn.so_du) — M4 fail-soft."""
    sql = "SELECT COALESCE(SUM(so_du), 0)::float FROM ketoan.quy_dn"
    return _safe_scalar(db, sql)


# ─── endpoint ────────────────────────────────────────────────────────────────

def _max_pos(*vals: float) -> float:
    """Trả max của các giá trị (>=0); dùng để tránh aggregate=0 đè data legacy."""
    return max([v for v in vals if v is not None] + [0.0])


@router.get("/can-doi")
def bao_cao_can_doi(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    thang: Optional[str] = Query(None, description="YYYY-MM (default tháng hiện tại)"),
    source: str = Query(
        "auto",
        description="auto: max(journal,legacy); journal: chỉ journal_line; legacy: chỉ bảng nguồn",
    ),
):
    """Balance sheet snapshot tại cuối tháng `thang`.

    `source`:
      - 'auto'    (mặc định): mỗi mục lấy MAX(journal_aggregate, legacy_query)
                  → tránh aggregate=0 đè dữ liệu legacy chưa post journal.
      - 'journal' : chỉ dùng journal aggregates (debug double-entry).
      - 'legacy'  : chỉ dùng query bảng nguồn (M1/M4/cong_no...) như bản trước.

    Response shape (M5 chuẩn):
      {
        "thang": "YYYY-MM",
        "tai_san": {tien_va_td, phai_thu, hang_ton_kho, tscd_rong, tong_tai_san},
        "nguon_von": {no_phai_tra, von_csh, tong_nguon_von},
        "check": {lech, can_bang, warning}
      }
    """
    thang, tu, den = _resolve_thang(thang)

    if source not in ("auto", "journal", "legacy"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "source phải ∈ auto | journal | legacy",
        )

    # ─── Journal aggregates (Phase 2 — double-entry) ────────────
    aggs: dict[str, float] = {}
    if source != "legacy":
        try:
            aggs = get_balance_sheet_aggregates(db, den)
        except (ProgrammingError, OperationalError):
            db.rollback()
            aggs = {}

    def _agg(code: str) -> float:
        return float(aggs.get(code, 0) or 0)

    # ─── TÀI SẢN ───────────────────────────────────────────
    # TK NH + Tiền mặt: LUÔN dùng canonical _balance_by_loai (match Tài Khoản
    # NH page = SoDuDauKy + SoQuy) bất kể source. Tránh _agg("112")/("111")
    # double-count vì M4 + SoQuy mirror cùng giao dịch (báo cáo phồng gấp đôi).
    canonical_tk_nh = _tk_ngan_hang_net(db, den)
    canonical_tien_mat = _tien_mat_so_quy_net(db, den)
    # TSCĐ ròng = (211 + 213) - 214 (journal) hoặc nguyen_gia - hao_mon (legacy)
    if source == "journal":
        tk_nh = canonical_tk_nh
        tien_mat = canonical_tien_mat
        phai_thu = _agg("131")
        hang_ton_kho = _agg("156")
        tscd_nguyen_gia = _agg("211") + _agg("213")
        tscd_hao_mon = _agg("214")
        tscd_rong = tscd_nguyen_gia - tscd_hao_mon
    else:
        legacy_phai_thu = _phai_thu(db, den)
        legacy_ton_kho = _hang_ton_kho(db)
        legacy_tscd_ng, legacy_tscd_hm = _tscd_breakdown(db, den)
        legacy_tscd = max(0.0, legacy_tscd_ng - legacy_tscd_hm)
        if source == "auto":
            tk_nh = canonical_tk_nh
            tien_mat = canonical_tien_mat
            phai_thu = _max_pos(_agg("131"), legacy_phai_thu)
            hang_ton_kho = _max_pos(_agg("156"), legacy_ton_kho)
            journal_tscd_ng = _agg("211") + _agg("213")
            journal_tscd_hm = _agg("214")
            journal_tscd_rong = journal_tscd_ng - journal_tscd_hm
            # max-positive giữa journal và legacy (tránh =0 đè data legacy)
            tscd_nguyen_gia = _max_pos(journal_tscd_ng, legacy_tscd_ng)
            tscd_hao_mon = _max_pos(journal_tscd_hm, legacy_tscd_hm)
            tscd_rong = _max_pos(journal_tscd_rong, legacy_tscd)
        else:  # legacy
            tk_nh = canonical_tk_nh
            tien_mat = canonical_tien_mat
            phai_thu = legacy_phai_thu
            hang_ton_kho = legacy_ton_kho
            tscd_nguyen_gia = legacy_tscd_ng
            tscd_hao_mon = legacy_tscd_hm
            tscd_rong = legacy_tscd

    # Tổng Tiền & TGNH = Σ 3 TK ngân hàng (ACB/VPB/BIDV) + sổ quỹ tiền mặt.
    # (2026-06-20: bỏ catch-all "chưa phân loại" — tiền vay đã gán đúng TK Tiền Mặt;
    #  nếu phát sinh so_quy thiếu TK thì sửa ở nguồn, không gom ẩn vào cân đối.)
    tien_va_td_tong = tk_nh + tien_mat
    tong_tai_san = tien_va_td_tong + phai_thu + hang_ton_kho + tscd_rong

    # ─── NGUỒN VỐN — Nợ phải trả ──────────────────────────
    if source == "journal":
        phai_tra_ncc = _agg("331")
        vay_nh = _agg("311")
        vay_dh = _agg("341")
        phai_tra_nv = _agg("334")
    else:
        legacy_ncc = _phai_tra_ncc(db, den)
        legacy_vay_nh, legacy_vay_dh = _vay_ngan_han_dai_han(db, den)
        if source == "auto":
            phai_tra_ncc = _max_pos(_agg("331"), legacy_ncc)
            vay_nh = _max_pos(_agg("311"), legacy_vay_nh)
            vay_dh = _max_pos(_agg("341"), legacy_vay_dh)
            phai_tra_nv = _agg("334")
        else:  # legacy
            phai_tra_ncc = legacy_ncc
            vay_nh = legacy_vay_nh
            vay_dh = legacy_vay_dh
            phai_tra_nv = 0.0

    no_phai_tra_tong = phai_tra_ncc + vay_nh + vay_dh + phai_tra_nv

    # ─── NGUỒN VỐN — Vốn CSH ──────────────────────────────
    if source == "journal":
        von_gop = _agg("411")
        # Quỹ DN: 414 + 415 + 353
        quy_dn = _agg("414") + _agg("415") + _agg("353")
        ln_giu_lai = _agg("421")
    else:
        legacy_von = _von_gop(db, den)
        legacy_quy = _quy_dn_tong(db)
        legacy_ln = _ln_giu_lai(db, thang)
        if source == "auto":
            von_gop = _max_pos(_agg("411"), legacy_von)
            quy_dn = _max_pos(
                _agg("414") + _agg("415") + _agg("353"), legacy_quy,
            )
            # LN giữ lại có thể âm — không dùng max, ưu tiên legacy nếu có
            ln_giu_lai = legacy_ln if legacy_ln else _agg("421")
        else:
            von_gop = legacy_von
            quy_dn = legacy_quy
            ln_giu_lai = legacy_ln

    von_csh_tong = von_gop + ln_giu_lai + quy_dn

    tong_nguon_von = no_phai_tra_tong + von_csh_tong
    lech = tong_tai_san - tong_nguon_von
    can_bang = abs(lech) < 1.0

    warnings: list[str] = []
    if not can_bang:
        warnings.append(
            f"Lệch {lech:,.0f} đ — nguyên nhân thường gặp:"
        )
        warnings.append(
            " (1) Bút toán double-entry chưa đầy đủ — "
            "kiểm tra GET /api/journal/balance-summary;"
        )
        warnings.append(
            " (2) Kỳ chưa chốt → LN giữ lại chưa cộng được;"
        )
        warnings.append(
            " (3) M1/M4 bảng (inventory_balance/von_chu_so_huu/quy_dn) chưa migrate;"
        )
        warnings.append(
            " (4) Số dư đầu kỳ TK ngân hàng chưa khai báo;"
        )
        warnings.append(
            " (5) Lương phải trả NV (334) phase 2 chưa tính."
        )

    return {
        "thang": thang,
        "source": source,
        "tai_san": {
            "tien_va_td": {
                "tk_ngan_hang": tk_nh,
                "tien_mat_so_quy": tien_mat,
                "tong": tien_va_td_tong,
            },
            "phai_thu": phai_thu,
            "hang_ton_kho": hang_ton_kho,
            "tscd_nguyen_gia": tscd_nguyen_gia,
            "tscd_hao_mon_luy_ke": tscd_hao_mon,
            "tscd_rong": tscd_rong,
            "tong_tai_san": tong_tai_san,
        },
        "nguon_von": {
            "no_phai_tra": {
                "phai_tra_ncc": phai_tra_ncc,
                "vay_ngan_han": vay_nh,
                "vay_dai_han": vay_dh,
                "phai_tra_nv": phai_tra_nv,
                "tong": no_phai_tra_tong,
            },
            "von_csh": {
                "von_gop": von_gop,
                "ln_giu_lai": ln_giu_lai,
                "quy_dn": quy_dn,
                "tong": von_csh_tong,
            },
            "tong_nguon_von": tong_nguon_von,
        },
        "journal_aggregates": aggs,
        "check": {
            "lech": lech,
            "can_bang": can_bang,
            "warning": " ".join(warnings) if warnings else None,
        },
    }
