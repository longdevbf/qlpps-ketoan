"""Báo Cáo Cân Đối Tài Chính (Balance Sheet) — refactor M5.

Endpoint:
    GET /api/bao-cao/can-doi?thang=YYYY-MM

Hai vế:
  TÀI SẢN
    1. Tiền & tương đương: tk_ngan_hang (M4 tai_khoan_nh_giao_dich) + tien_mat_so_quy
    2. Phải thu KH (cong_no loai='phai_thu', còn lại)
    3. Hàng tồn kho (sổ ketoan.inventory_movement nhập − xuất đến ngày xem)
    4. TSCĐ ròng (phase 2 — 0)
  NGUỒN VỐN
    1. Nợ phải trả: phai_tra_ncc + vay_ngan_han + vay_dai_han + phai_tra_nv (phase 2 = 0)
    2. Vốn chủ sở hữu: von_gop + ln_giu_lai + quy_dn

Cross-app reads (M1/M4 bảng có thể chưa migrate) dùng raw SQL `text()` fail-soft.
"""
from calendar import monthrange
from datetime import date as date_cls, timedelta
from decimal import Decimal
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

from shared.auth import JWTPayload
from shared.db import get_db

from ..models import CongNo, KyKeToan
from ..services.journal import get_balance_sheet_aggregates
from ..services.loi_doc import bat_dau_ghi_loi, ghi_loi_doc
from ..services.nguon_can_doi import ghep_nguon_can_doi, nguyen_nhan_lech
from ..services.so_quy_auto import so_du_truoc_ngay
from ._deps import require_ketoan_user
from ..services.cd_chi_tiet import (
    KHOAN as KHOAN_CD,
    SO_DONG_MAC_DINH as SO_DONG_MAC_DINH_CD,
    SO_DONG_TOI_DA as SO_DONG_TOI_DA_CD,
    _lay as _lay_so_cd,
    chi_tiet as chi_tiet_dong_cd,
    CONG_THUC as CONG_THUC_CD,
    chi_tiet_cong_thuc as chi_tiet_cong_thuc_cd,
)


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


# ─── helpers ─────────────────────────────────────────────────────────────────

def _f(v: Any) -> float:
    return float(v or 0)


def _safe_scalar(db: Session, sql: str, default: float = 0.0, **params) -> float:
    try:
        v = db.execute(text(sql), params).scalar()
        return float(v or 0)
    except ProgrammingError as _loi:
        ghi_loi_doc(db, _loi)
        return float(default)


def _safe_rows(db: Session, sql: str, **params) -> list:
    try:
        return db.execute(text(sql), params).all()
    except ProgrammingError as _loi:
        ghi_loi_doc(db, _loi)
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
    """Số dư HẾT NGÀY `on_date` của tất cả TK theo `loai` (ngan_hang/tien_mat).

    Một nguồn sự thật với màn Sổ quỹ / Ngân hàng / LCTT (mã 60, 70):
    `so_quy_auto.so_du_truoc_ngay(tk, on_date + 1)` — thuật toán neo SoDuDauKy
    (neo gần nhất ≤ tháng → cộng dồn; không có → neo tương lai trừ ngược; không có
    neo nào → so_du_dau + toàn bộ giao dịch).

    QA 25/09/2026: bản trước chỉ dùng SoDuDauKy khi có snapshot ĐÚNG tháng của
    on_date, còn lại cộng dồn MỌI giao dịch từ đầu (bỏ qua snapshot 01/05/2026)
    → tiền cuối 09/2026 trên Cân đối = 1,36 tỷ trong khi Sổ quỹ / LCTT = 97 triệu.
    KHÔNG cộng `tai_khoan_nh_giao_dich` (M4) vì M4 mirror SoQuy → double-count.
    """
    rows = _safe_rows(
        db,
        """
        SELECT id, ten_tk
        FROM ketoan.tai_khoan_nh
        WHERE COALESCE(active, true) = true AND loai = :loai
        """,
        loai=loai,
    )
    ngay_sau = on_date + timedelta(days=1)
    return float(sum((so_du_truoc_ngay(db, tk_id, ten_tk, ngay_sau) for tk_id, ten_tk in rows), Decimal("0")))


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


def _hang_ton_kho(db: Session, on_date: date_cls) -> float:
    """Giá trị tồn kho TẠI `on_date` = Σ(nhập − xuất) của sổ `inventory_movement` đến ngày đó.

    Trước 2026-09-25 lấy SUM(inventory_balance.gia_tri_ton) — số HIỆN TẠI bất kể ngày xem
    → xem tháng cũ / "số đầu năm" bị sai. Ngoài ra bảng balance KHÔNG trừ 5 phiếu xuất
    giá vốn từ saleadmin (VH-*-COGS, 19.255.000đ) dù sổ movement + bút toán 632/156 đã ghi
    → balance đang cao hơn sổ kho đúng bằng số đó (giá vốn đã vào P&L mà tài sản vẫn còn).
    Sản phẩm có tồn trong balance nhưng CHƯA có dòng movement nào (tồn đầu kỳ nhập tay)
    không dựng được lịch sử → cộng số hiện tại của nó (hiện DB không có SP nào như vậy).
    """
    sql = """
        SELECT
          COALESCE((SELECT SUM(CASE WHEN loai = 'nhap' THEN thanh_tien
                                    WHEN loai = 'xuat' THEN -thanh_tien
                                    -- điều chỉnh (kiểm kê) ghi thanh_tien CÓ DẤU
                                    WHEN loai = 'dieu_chinh' THEN thanh_tien ELSE 0 END)
                    FROM ketoan.inventory_movement WHERE ngay <= :on_date), 0)
          + COALESCE((SELECT SUM(b.gia_tri_ton) FROM ketoan.inventory_balance b
                      WHERE NOT EXISTS (SELECT 1 FROM ketoan.inventory_movement m
                                        WHERE m.product_id = b.product_id)), 0)
    """
    return _safe_scalar(db, sql, on_date=on_date)


def _tscd_breakdown(db: Session, on_date: date_cls) -> tuple[float, float]:
    """TSCĐ tại `on_date` từ `tai_san_co_dinh` + `khau_hao_log`. Returns (nguyen_gia, hao_mon).

    - Phạm vi: TS đã đưa vào sử dụng (ngay_su_dung <= on_date) và CHƯA thanh lý tại ngày đó
      (đang dùng, hoặc ngay_thanh_ly > on_date).
    - Hao mòn luỹ kế TẠI on_date = hao_mon_luy_ke_sau của dòng khấu hao cuối cùng có
      thang <= tháng của on_date. Chưa tới dòng log đầu → phần hao mòn có sẵn trước log
      (log đầu: hao_mon_luy_ke_sau − so_tien). TS không có log nào → dùng số hiện tại
      (không có lịch sử để lùi). Trước 2026-09-25 luôn lấy hao_mon_luy_ke HIỆN TẠI.
    """
    sql = """
        WITH ts AS (
            SELECT id, nguyen_gia, hao_mon_luy_ke
            FROM ketoan.tai_san_co_dinh
            WHERE ngay_su_dung <= :on_date
              AND (trang_thai = 'dang_su_dung'
                   OR (ngay_thanh_ly IS NOT NULL AND ngay_thanh_ly > :on_date))
        )
        SELECT
            COALESCE(SUM(ts.nguyen_gia), 0)::float,
            COALESCE(SUM(
                CASE
                  WHEN den.hm IS NOT NULL THEN den.hm
                  WHEN dau.hm0 IS NOT NULL THEN dau.hm0
                  ELSE ts.hao_mon_luy_ke
                END), 0)::float
        FROM ts
        LEFT JOIN LATERAL (
            SELECT hao_mon_luy_ke_sau AS hm FROM ketoan.khau_hao_log l
            WHERE l.tscd_id = ts.id AND l.thang <= to_char(CAST(:on_date AS date), 'YYYY-MM')
            ORDER BY l.thang DESC, l.id DESC LIMIT 1
        ) den ON TRUE
        LEFT JOIN LATERAL (
            SELECT hao_mon_luy_ke_sau - so_tien AS hm0 FROM ketoan.khau_hao_log l
            WHERE l.tscd_id = ts.id ORDER BY l.thang, l.id LIMIT 1
        ) dau ON TRUE
    """
    rows = _safe_rows(db, sql, on_date=on_date)
    if not rows:
        return 0.0, 0.0
    return float(rows[0][0] or 0), float(rows[0][1] or 0)


# ─── NGUỒN VỐN ───────────────────────────────────────────────────────────────

def _phai_tra_ncc(db: Session, on_date: date_cls) -> tuple[float, float, float]:
    """Trả (thực+cần kiểm, dự kiến, cần kiểm riêng) — quyết định người dùng 30/09/2026:
    mã 331 CHỈ cộng nợ THỰC; nợ DỰ KIẾN thành dòng ghi chú riêng dưới bảng, không cộng vào
    tổng nguồn vốn; "cần kiểm" vẫn nằm trong 331 (giữ hành vi cũ) nhưng ghi chú riêng số tiền.

    REFACTOR 2026-09-30 (migration q7): nối PO gộp vào view theo dòng
    ketoan.v_cong_no_phai_tra_phan_loai (thay 2 JOIN muahang.purchase_orders + v_nhom_no_don
    lặp lại ở đây và ở cong_no_ncc.py/cong_no_dong_bo.py) — đã kiểm SQL trực tiếp trên dev:
    0 dòng lệch nhom_no so với công thức cũ (REGEXP_MATCH + tra ma_bao_gia cho dòng cọc/trả
    trước) trước khi đổi.
    """
    rows = db.execute(text("""
        SELECT vw.nhom_no, cn.con_lai
        FROM ketoan.cong_no cn
        JOIN ketoan.v_cong_no_phai_tra_phan_loai vw ON vw.id = cn.id
        WHERE cn.loai = 'phai_tra' AND cn.ngay <= :on_date AND cn.trang_thai != 'da_tra'
    """), {"on_date": on_date}).mappings().all()
    thuc_va_can_kiem = 0.0
    du_kien = 0.0
    can_kiem = 0.0
    for r in rows:
        con_lai = _f(r["con_lai"])
        if r["nhom_no"] == "du_kien":
            du_kien += con_lai
        else:
            thuc_va_can_kiem += con_lai
            if r["nhom_no"] == "can_kiem":
                can_kiem += con_lai
    return thuc_va_can_kiem, du_kien, can_kiem


def _tra_truoc_da_tra_ncc(db: Session, on_date: date_cls) -> float:
    """BẢN VÁ 30/09/2026 mục 5: `_phai_tra_ncc` lọc `trang_thai != 'da_tra'` nên bỏ hẳn các dòng
    NCC đã đánh dấu "đã trả" mà `con_lai` vẫn ÂM (đã ứng/trả nhiều hơn hoá đơn — production đã
    thấy: CN-2026-0036 A TUẤN −40tr, CN-2026-0149 A ĐỊNH SƠN PU −1tr, CN-2026-0240 CHIẾN PHƯƠNG
    −78tr, cộng 119.000.000). Số này KHÔNG cộng vào 331 (không đổi công thức/số 331 hiện có) — chỉ
    dùng cho một dòng ghi chú riêng dưới bảng Cân đối để không giấu khoản tiền công ty đang ứng.

    Trả SỐ DƯƠNG (đổi dấu con_lai âm) — đúng ý "chưa gồm X đ" ở Cân đối/kt-cdkt.js.
    """
    rows = db.execute(text("""
        SELECT cn.con_lai
        FROM ketoan.cong_no cn
        JOIN ketoan.v_cong_no_phai_tra_phan_loai vw ON vw.id = cn.id
        WHERE cn.loai = 'phai_tra' AND cn.ngay <= :on_date
          AND cn.trang_thai = 'da_tra' AND cn.con_lai < 0
          AND vw.nhom_no != 'du_kien'
    """), {"on_date": on_date}).mappings().all()
    return -sum(_f(r["con_lai"]) for r in rows)


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
    loi_doc = bat_dau_ghi_loi()

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
        except ProgrammingError as _loi:
            ghi_loi_doc(db, _loi)
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
        legacy_ton_kho = _hang_ton_kho(db, den)
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
    # Tạm ứng nhân viên (TK 141, màn /ketoan/tam-ung, 2026-09-25) — chỉ có trên
    # journal. Theo B01-DN, 141 nằm trong "Các khoản phải thu ngắn hạn" (mã 130)
    # nên gộp vào phai_thu; thiếu dòng này thì tiền chi tạm ứng (sổ quỹ giảm)
    # làm tổng tài sản hụt đúng bằng số dư 141 → bảng cân đối lệch.
    tam_ung = _agg("141")
    phai_thu += tam_ung
    tong_tai_san = tien_va_td_tong + phai_thu + hang_ton_kho + tscd_rong

    # ─── NGUỒN VỐN — Nợ phải trả ──────────────────────────
    # 30/09/2026: mã 331 chỉ cộng nợ THỰC (+ cần kiểm, giữ hành vi cũ) — dự kiến tách riêng,
    # KHÔNG cộng vào tổng nguồn vốn. ncc_du_kien/ncc_can_kiem chỉ để ghi chú, không cộng thêm.
    ncc_du_kien = 0.0
    ncc_can_kiem = 0.0
    if source == "journal":
        phai_tra_ncc = _agg("331")
        vay_nh = _agg("311")
        vay_dh = _agg("341")
        phai_tra_nv = _agg("334")
    else:
        legacy_ncc, ncc_du_kien, ncc_can_kiem = _phai_tra_ncc(db, den)
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

    # BẢN VÁ 30/09/2026 mục 5: ghi chú riêng — KHÔNG cộng vào phai_tra_ncc/no_phai_tra_tong ở
    # trên, KHÔNG đổi công thức 331. Luôn tính (độc lập với source) vì đây chỉ minh bạch thêm.
    ncc_tra_truoc_da_tra = _tra_truoc_da_tra_ncc(db, den)

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

    # ─── Đợt 1 (07/10/2026): khai nguồn từng dòng + nguyên nhân lệch — CHỈ THÊM trường, không
    # đổi số nào ở trên. Chế độ auto lấy MAX(sổ cái, bảng nghiệp vụ) cho từng dòng → ghi lại cả
    # hai số và số nào đang được dùng, để màn /ketoan/doi-chieu và tooltip báo cáo hiện ra.
    gia_tri = {
        "tai_san.tien_va_td.tien_mat_so_quy": tien_mat,
        "tai_san.tien_va_td.tk_ngan_hang": tk_nh,
        "tai_san.phai_thu": phai_thu,
        "tai_san.hang_ton_kho": hang_ton_kho,
        "tai_san.tscd_nguyen_gia": tscd_nguyen_gia,
        "tai_san.tscd_hao_mon_luy_ke": tscd_hao_mon,
        "nguon_von.no_phai_tra.phai_tra_ncc": phai_tra_ncc,
        "nguon_von.no_phai_tra.vay_ngan_han": vay_nh,
        "nguon_von.no_phai_tra.vay_dai_han": vay_dh,
        "nguon_von.no_phai_tra.phai_tra_nv": phai_tra_nv,
        "nguon_von.von_csh.von_gop": von_gop,
        "nguon_von.von_csh.quy_dn": quy_dn,
        "nguon_von.von_csh.ln_giu_lai": ln_giu_lai,
    }
    so_cai: dict[str, float] = {} if source == "legacy" else {
        "tai_san.tien_va_td.tien_mat_so_quy": _agg("111"),
        "tai_san.tien_va_td.tk_ngan_hang": _agg("112"),
        "tai_san.phai_thu": _agg("131") + tam_ung,
        "tai_san.hang_ton_kho": _agg("156"),
        "tai_san.tscd_nguyen_gia": _agg("211") + _agg("213"),
        "tai_san.tscd_hao_mon_luy_ke": _agg("214"),
        "nguon_von.no_phai_tra.phai_tra_ncc": _agg("331"),
        "nguon_von.no_phai_tra.vay_ngan_han": _agg("311"),
        "nguon_von.no_phai_tra.vay_dai_han": _agg("341"),
        "nguon_von.no_phai_tra.phai_tra_nv": _agg("334"),
        "nguon_von.von_csh.von_gop": _agg("411"),
        "nguon_von.von_csh.quy_dn": _agg("414") + _agg("415") + _agg("353"),
        "nguon_von.von_csh.ln_giu_lai": _agg("421"),
    }
    # Tiền luôn đọc sổ quỹ / TK ngân hàng ở mọi chế độ nên luôn có số nghiệp vụ.
    nghiep_vu: dict[str, float] = {
        "tai_san.tien_va_td.tien_mat_so_quy": canonical_tien_mat,
        "tai_san.tien_va_td.tk_ngan_hang": canonical_tk_nh,
    }
    if source != "journal":
        nghiep_vu.update({
            "tai_san.phai_thu": legacy_phai_thu + tam_ung,
            "tai_san.hang_ton_kho": legacy_ton_kho,
            "tai_san.tscd_nguyen_gia": legacy_tscd_ng,
            "tai_san.tscd_hao_mon_luy_ke": legacy_tscd_hm,
            "nguon_von.no_phai_tra.phai_tra_ncc": legacy_ncc,
            "nguon_von.no_phai_tra.vay_ngan_han": legacy_vay_nh,
            "nguon_von.no_phai_tra.vay_dai_han": legacy_vay_dh,
            "nguon_von.von_csh.von_gop": legacy_von,
            "nguon_von.von_csh.quy_dn": legacy_quy,
            "nguon_von.von_csh.ln_giu_lai": legacy_ln,
        })
    # Ghép nguồn + nguyên nhân lệch ở services/nguon_can_doi.py (router chỉ gom số của chính nó).
    nguon = ghep_nguon_can_doi(gia_tri, so_cai, nghiep_vu)
    nguyen_nhan: list[dict] = [] if can_bang else nguyen_nhan_lech(
        db, thang=thang, von_csh_tong=von_csh_tong, von_gop=von_gop,
        ln_giu_lai=ln_giu_lai, quy_dn=quy_dn, nguon=nguon,
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
            "tam_ung": tam_ung,  # đã nằm trong phai_thu
            "hang_ton_kho": hang_ton_kho,
            "tscd_nguyen_gia": tscd_nguyen_gia,
            "tscd_hao_mon_luy_ke": tscd_hao_mon,
            "tscd_rong": tscd_rong,
            "tong_tai_san": tong_tai_san,
        },
        "nguon_von": {
            "no_phai_tra": {
                "phai_tra_ncc": phai_tra_ncc,
                # 30/09/2026: ghi chú riêng, KHÔNG cộng vào phai_tra_ncc/tong ở trên — đơn NCC
                # còn đang chạy (đặt hàng/đang SX/đã có hàng), chưa được coi là nợ đã chốt.
                "phai_tra_ncc_du_kien": ncc_du_kien,
                # Đã NẰM TRONG phai_tra_ncc (nhóm 'can_kiem' gộp vào thực, giữ hành vi cũ) — trường
                # này chỉ để hiển thị riêng, không cộng thêm.
                "phai_tra_ncc_can_kiem": ncc_can_kiem,
                # BẢN VÁ 30/09/2026 mục 5: KHÔNG nằm trong phai_tra_ncc — dòng NCC đã đánh dấu
                # "đã trả" (trang_thai='da_tra') nhưng con_lai vẫn âm (ứng/trả nhiều hơn hoá đơn),
                # bị _phai_tra_ncc loại hẳn vì lọc trang_thai != 'da_tra'. Chỉ để ghi chú minh bạch.
                "phai_tra_ncc_tra_truoc_da_tra": ncc_tra_truoc_da_tra,
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
            "nguyen_nhan": nguyen_nhan,
        },
        "nguon": nguon,
        # Bảng/cột không đọc được (ProgrammingError) — số 0 ở các dòng liên quan KHÔNG phải số thật.
        "loi_doc_du_lieu": loi_doc,
    }


# ════════════════════════════════════════════════════════════════════════════
# Chi tiết từng dòng — "con số này ở đâu ra"
# ════════════════════════════════════════════════════════════════════════════

@router.get("/can-doi/chi-tiet")
def bao_cao_can_doi_chi_tiet(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, Depends(require_ketoan_user)],
    khoa: str = Query(..., description="Khoá dòng, vd 'tai_san.phai_thu'"),
    thang: Optional[str] = Query(None, description="YYYY-MM; mặc định tháng hiện tại"),
    source: str = Query("auto"),
    trang: int = Query(1, ge=1),
    so_dong: int = Query(SO_DONG_MAC_DINH_CD, ge=1, le=SO_DONG_TOI_DA_CD),
):
    """Các chứng từ gốc làm nên một dòng Cân đối kế toán, có phân trang.

    `tong` trả về đọc THẲNG từ `bao_cao_can_doi()` nên luôn đúng bằng số người dùng
    đang nhìn, kể cả khi chế độ 'auto' chọn số từ sổ cái thay vì sổ cũ. Khi danh sách
    chứng từ cộng lại không khớp `tong`, trường `ghi_chu` nói rõ — chênh đó là dấu
    hiệu sổ cái và sổ cũ đang lệch nhau, không phải lỗi của popup.
    """
    if khoa in CONG_THUC_CD:
        bc = bao_cao_can_doi(db, user, thang=thang, source=source)
        _t, _tu, den = _resolve_thang(thang)
        return chi_tiet_cong_thuc_cd(khoa, bc, den)
    kh = KHOAN_CD.get(khoa)
    if kh is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, {
            "loi": "khoa_chua_khai",
            "thong_bao": f"Không có dòng '{khoa}' trong Cân đối kế toán.",
            "khoa_dang_co": sorted(list(KHOAN_CD.keys()) + list(CONG_THUC_CD.keys())),
        })
    bc = bao_cao_can_doi(db, user, thang=thang, source=source)
    _thang, _tu, den = _resolve_thang(thang)
    so_bc = _lay_so_cd(bc, kh["duong_dan"])
    return chi_tiet_dong_cd(db, khoa, den, so_bc, trang=trang, so_dong=so_dong)
