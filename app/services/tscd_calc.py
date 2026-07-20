"""Phase 3 — Tài Sản Cố Định + Khấu Hao (đường thẳng).

API chính:
    next_ma_tscd(db)                              — gen 'TS-YYYY-NNN'
    chay_khau_hao_thang(db, thang, by_user)       — chạy khấu hao tháng
    mua_tscd(db, tscd, tai_khoan_id, by_user)     — post JE mua TSCĐ
    thanh_ly_tscd(db, tscd_id, gia_thanh_ly,
                  ngay, tai_khoan_id, by_user)    — post JE thanh lý

Account TT200:
    - 211 TSCĐ HH; 213 TSCĐ vô hình
    - 214 Hao mòn lũy kế (contra-asset, credit balance)
    - 641 CP BH | 642 CP QL | 635 CP TC | 811 CP khác (theo bo_phan)
    - 711 Thu nhập khác (lãi thanh lý) | 811 CP khác (lỗ thanh lý)
    - 111 tiền mặt | 112 tiền gửi NH (theo TaiKhoanNH.loai)
"""
from calendar import monthrange
from datetime import date as date_cls, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    JournalEntry, KhauHaoLog, SoQuy, TaiKhoanNH, TaiKhoanNHGiaoDich,
    TaiSanCoDinh,
)
from .journal import post_journal


# ─── Helpers ──────────────────────────────────────────────────────────────────

_BO_PHAN_TO_ACCOUNT: dict[str, str] = {
    "ban_hang": "641",
    "quan_ly": "642",
    "tai_chinh": "635",
    "khac": "811",
}


def _q2(x: Decimal) -> Decimal:
    """Round Decimal về 2 chữ số thập phân (HALF_UP)."""
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_dec(x) -> Decimal:
    if x is None:
        return Decimal("0")
    return x if isinstance(x, Decimal) else Decimal(str(x))


def _cash_account(tk: Optional[TaiKhoanNH]) -> str:
    if tk is None:
        return "112"
    return "111" if (tk.loai or "").strip() == "tien_mat" else "112"


def _kh_expense_account(bo_phan: str) -> str:
    """Map bộ phận → account chi phí khấu hao."""
    return _BO_PHAN_TO_ACCOUNT.get((bo_phan or "quan_ly").strip(), "642")


def _last_day_of_month(thang: str) -> date_cls:
    """thang 'YYYY-MM' → ngày cuối tháng."""
    yr, mo = int(thang[:4]), int(thang[5:7])
    return date_cls(yr, mo, monthrange(yr, mo)[1])


def _validate_thang(thang: str) -> str:
    import re
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", thang):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"thang phải dạng YYYY-MM, nhận: {thang!r}",
        )
    return thang


# ─── ID generator TS-YYYY-NNN ─────────────────────────────────────────────────

def next_ma_tscd(db: Session) -> str:
    """Sinh mã TSCĐ mới: TS-YYYY-NNN.

    Lấy max sequence năm hiện tại + 1. Race-condition acceptable cho dev;
    production nên dùng SEQUENCE riêng hoặc advisory lock.
    """
    year = datetime.now().year
    prefix = f"TS-{year}-"
    rows = db.execute(
        select(TaiSanCoDinh.ma_tscd).where(TaiSanCoDinh.ma_tscd.like(f"{prefix}%"))
    ).all()
    max_seq = 0
    for (m,) in rows:
        try:
            seq = int(m[len(prefix):])
            if seq > max_seq:
                max_seq = seq
        except (ValueError, TypeError):
            continue
    return f"{prefix}{max_seq + 1:03d}"


# ─── mua_tscd: post JE mua TSCĐ + ghi giao dịch TK NH ────────────────────────

def mua_tscd(
    db: Session,
    *,
    tscd: TaiSanCoDinh,
    tai_khoan_id: int,
    by_user: Optional[str],
) -> JournalEntry:
    """Post bút toán mua TSCĐ:

    Nợ 211 (HH) hoặc 213 (VH) — nguyên giá
    Có 111/112 — tiền chi
    Đồng thời insert tai_khoan_nh_giao_dich loai='chi' để cập nhật số dư TK.

    Yêu cầu `tscd` đã được flush (có id) trước khi gọi.
    """
    tk = db.get(TaiKhoanNH, tai_khoan_id)
    if not tk:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"tai_khoan_id={tai_khoan_id} không tồn tại",
        )
    cash_acc = _cash_account(tk)
    asset_acc = "213" if tscd.loai == "vo_hinh" else "211"

    gd = TaiKhoanNHGiaoDich(
        ngay=tscd.ngay_mua,
        tai_khoan_id=tk.id,
        loai="chi",
        so_tien=tscd.nguyen_gia,
        doi_tac=tscd.ncc or None,
        ghi_chu=f"Mua TSCĐ {tscd.ma_tscd} — {tscd.ten_tscd}",
        source_app="ketoan",
        source_doc_id=f"tscd_{tscd.id}",
        created_by=by_user,
    )
    db.add(gd)
    db.flush()

    # Auto-write sổ quỹ chi (phân loại CF: mua_ccdc)
    sq = SoQuy(
        ngay=tscd.ngay_mua,
        loai="chi",
        so_tien=tscd.nguyen_gia,
        tai_khoan=tk.ten_tk,
        noi_dung=f"Mua TSCĐ {tscd.ma_tscd} — {tscd.ten_tscd}",
        phan_loai_cf="mua_ccdc",
        lien_quan="tscd",
        ref_id=str(tscd.id),
        created_by=by_user,
    )
    db.add(sq)
    db.flush()

    je = post_journal(
        db,
        ngay=tscd.ngay_mua,
        mo_ta=f"Mua TSCĐ {tscd.ma_tscd} — {tscd.ten_tscd}",
        source_type="mua_tscd",
        source_id=str(tscd.id),
        by_user=by_user,
        lines=[
            {
                "loai": "no", "account_code": asset_acc,
                "ref_table": "tai_san_co_dinh", "ref_id": tscd.id,
                "so_tien": tscd.nguyen_gia,
                "ghi_chu": f"Nguyên giá TSCĐ {tscd.ma_tscd}",
            },
            {
                "loai": "co", "account_code": cash_acc,
                "ref_table": "tai_khoan_nh", "ref_id": tk.id,
                "so_tien": tscd.nguyen_gia,
                "ghi_chu": f"Chi từ {tk.ten_tk}",
            },
        ],
    )
    return je


# ─── chay_khau_hao_thang: chạy khấu hao tháng ────────────────────────────────

def chay_khau_hao_thang(
    db: Session,
    *,
    thang: str,
    by_user: Optional[str],
) -> dict:
    """Chạy khấu hao tháng `YYYY-MM`.

    Logic:
      1. List TSCĐ active (trang_thai='dang_su_dung', ngay_su_dung <= cuối tháng)
      2. Mỗi TSCĐ:
         - Skip nếu đã khấu hao tháng này (đã có khau_hao_log).
         - Skip nếu hao_mon_luy_ke >= nguyen_gia (đã khấu hao hết).
         - Tính so_tien_kh = ROUND(nguyen_gia / so_thang_kh, 2).
         - Nếu hao_mon + so_tien_kh > nguyen_gia → cap = nguyen_gia − hao_mon.
         - Post JE: Nợ 641|642|635|811 (theo bo_phan); Có 214.
         - Insert khau_hao_log + update tscd.hao_mon_luy_ke.
      3. Return summary dict.
    """
    thang = _validate_thang(thang)
    last_day = _last_day_of_month(thang)

    # List TSCĐ candidates (đang sử dụng + đã đến ngày sử dụng)
    items = db.execute(
        select(TaiSanCoDinh)
        .where(TaiSanCoDinh.trang_thai == "dang_su_dung")
        .where(TaiSanCoDinh.ngay_su_dung <= last_day)
        .order_by(TaiSanCoDinh.id)
    ).scalars().all()

    processed: list[dict] = []
    skipped: list[dict] = []
    tong_kh = Decimal("0")

    for tscd in items:
        # Đã khấu hao tháng này?
        existed = db.execute(
            select(KhauHaoLog.id)
            .where(KhauHaoLog.tscd_id == tscd.id)
            .where(KhauHaoLog.thang == thang)
        ).scalar()
        if existed:
            skipped.append({
                "tscd_id": tscd.id, "ma_tscd": tscd.ma_tscd,
                "ten_tscd": tscd.ten_tscd, "ly_do": "da_khau_hao",
            })
            continue

        nguyen_gia = _to_dec(tscd.nguyen_gia)
        hao_mon = _to_dec(tscd.hao_mon_luy_ke)
        if hao_mon >= nguyen_gia:
            skipped.append({
                "tscd_id": tscd.id, "ma_tscd": tscd.ma_tscd,
                "ten_tscd": tscd.ten_tscd, "ly_do": "da_khau_hao_het",
            })
            continue

        # Khấu hao đường thẳng
        so_tien = _q2(nguyen_gia / Decimal(tscd.so_thang_kh))
        # Cap ở tháng cuối — không vượt quá nguyên giá
        if hao_mon + so_tien > nguyen_gia:
            so_tien = _q2(nguyen_gia - hao_mon)
        if so_tien <= 0:
            skipped.append({
                "tscd_id": tscd.id, "ma_tscd": tscd.ma_tscd,
                "ten_tscd": tscd.ten_tscd, "ly_do": "da_khau_hao_het",
            })
            continue

        hao_mon_sau = _q2(hao_mon + so_tien)
        cp_acc = _kh_expense_account(tscd.bo_phan)

        je = post_journal(
            db,
            ngay=last_day,
            mo_ta=(
                f"Khấu hao {thang} — {tscd.ma_tscd} {tscd.ten_tscd} "
                f"({so_tien:,.0f} đ)"
            ),
            source_type="khau_hao",
            source_id=str(tscd.id),
            by_user=by_user,
            lines=[
                {
                    "loai": "no", "account_code": cp_acc,
                    "ref_table": "tai_san_co_dinh", "ref_id": tscd.id,
                    "so_tien": so_tien,
                    "ghi_chu": (
                        f"CP khấu hao {thang} {tscd.ma_tscd} "
                        f"({tscd.bo_phan})"
                    ),
                },
                {
                    "loai": "co", "account_code": "214",
                    "ref_table": "tai_san_co_dinh", "ref_id": tscd.id,
                    "so_tien": so_tien,
                    "ghi_chu": f"Hao mòn TSCĐ {tscd.ma_tscd}",
                },
            ],
        )

        log = KhauHaoLog(
            tscd_id=tscd.id, thang=thang,
            so_tien=so_tien, hao_mon_luy_ke_sau=hao_mon_sau,
            journal_id=je.id,
            ghi_chu=f"Đường thẳng — {tscd.so_thang_kh} tháng",
            created_by=by_user,
        )
        db.add(log)
        # Update hao mòn lũy kế
        tscd.hao_mon_luy_ke = hao_mon_sau
        db.flush()

        processed.append({
            "tscd_id": tscd.id,
            "ma_tscd": tscd.ma_tscd,
            "ten_tscd": tscd.ten_tscd,
            "so_tien_kh": so_tien,
            "hao_mon_luy_ke_sau": hao_mon_sau,
            "journal_id": je.id,
            "log_id": log.id,
        })
        tong_kh += so_tien

    return {
        "thang": thang,
        "da_xu_ly": len(processed),
        "tong_kh": tong_kh,
        "items": processed,
        "skipped": skipped,
    }


# ─── thanh_ly_tscd ────────────────────────────────────────────────────────────

def thanh_ly_tscd(
    db: Session,
    *,
    tscd_id: int,
    gia_thanh_ly: Decimal,
    ngay: date_cls,
    tai_khoan_id: Optional[int],
    ghi_chu: Optional[str],
    by_user: Optional[str],
) -> JournalEntry:
    """Thanh lý TSCĐ — bút toán phức:

      Nợ 214 hao_mon_luy_ke    (xoá hao mòn)
      Nợ 111/112 gia_thanh_ly  (nhận tiền — nếu có)
      Có 211/213 nguyen_gia    (xoá nguyên giá)
      Nếu lãi (gia_thanh_ly > còn lại) → Có 711 |lãi|
      Nếu lỗ (gia_thanh_ly < còn lại)  → Nợ 811 |lỗ|

    Đồng thời:
      - Insert tai_khoan_nh_giao_dich loai='thu' = gia_thanh_ly (nếu có TK).
      - Update tscd: trang_thai='da_thanh_ly', ngay_thanh_ly, gia_thanh_ly.
    """
    tscd = db.get(TaiSanCoDinh, tscd_id)
    if not tscd:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "TSCĐ không tồn tại")
    if tscd.trang_thai == "da_thanh_ly":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "TSCĐ đã thanh lý",
        )

    nguyen_gia = _to_dec(tscd.nguyen_gia)
    hao_mon = _to_dec(tscd.hao_mon_luy_ke)
    gia_tl = _q2(_to_dec(gia_thanh_ly))
    gia_tri_con_lai = _q2(nguyen_gia - hao_mon)
    lai_lo = _q2(gia_tl - gia_tri_con_lai)  # >0 lãi, <0 lỗ

    tk: Optional[TaiKhoanNH] = None
    cash_acc = "112"
    if tai_khoan_id:
        tk = db.get(TaiKhoanNH, tai_khoan_id)
        if not tk:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"tai_khoan_id={tai_khoan_id} không tồn tại",
            )
        cash_acc = _cash_account(tk)

    asset_acc = "213" if tscd.loai == "vo_hinh" else "211"

    # Build lines
    lines: list[dict] = []
    # Nợ 214 (xoá hao mòn) — chỉ thêm nếu có
    if hao_mon > 0:
        lines.append({
            "loai": "no", "account_code": "214",
            "ref_table": "tai_san_co_dinh", "ref_id": tscd.id,
            "so_tien": hao_mon,
            "ghi_chu": f"Xoá hao mòn TSCĐ {tscd.ma_tscd}",
        })
    # Nợ tiền nhận (nếu có)
    if gia_tl > 0:
        lines.append({
            "loai": "no", "account_code": cash_acc,
            "ref_table": "tai_khoan_nh", "ref_id": (tk.id if tk else None),
            "so_tien": gia_tl,
            "ghi_chu": (
                f"Thu thanh lý {tscd.ma_tscd}"
                + (f" vào {tk.ten_tk}" if tk else "")
            ),
        })
    # Có 211/213 nguyên giá
    lines.append({
        "loai": "co", "account_code": asset_acc,
        "ref_table": "tai_san_co_dinh", "ref_id": tscd.id,
        "so_tien": nguyen_gia,
        "ghi_chu": f"Xoá nguyên giá TSCĐ {tscd.ma_tscd}",
    })
    # Lãi/lỗ thanh lý
    if lai_lo > 0:
        lines.append({
            "loai": "co", "account_code": "711",
            "ref_table": "tai_san_co_dinh", "ref_id": tscd.id,
            "so_tien": lai_lo,
            "ghi_chu": f"Lãi thanh lý {tscd.ma_tscd}",
        })
    elif lai_lo < 0:
        lines.append({
            "loai": "no", "account_code": "811",
            "ref_table": "tai_san_co_dinh", "ref_id": tscd.id,
            "so_tien": -lai_lo,
            "ghi_chu": f"Lỗ thanh lý {tscd.ma_tscd}",
        })
    # Edge case: nếu hao_mon=0 và gia_tl=0 → không cân (chỉ Có nguyên giá).
    # Khi đó → coi nguyen_gia là lỗ thanh lý.
    if hao_mon == 0 and gia_tl == 0 and lai_lo == 0:
        # Recompute lai_lo as full loss
        lines.append({
            "loai": "no", "account_code": "811",
            "ref_table": "tai_san_co_dinh", "ref_id": tscd.id,
            "so_tien": nguyen_gia,
            "ghi_chu": f"Lỗ thanh lý {tscd.ma_tscd} (toàn bộ nguyên giá)",
        })

    # Ghi giao dịch TK NH (nếu có thu tiền)
    if tk and gia_tl > 0:
        gd = TaiKhoanNHGiaoDich(
            ngay=ngay,
            tai_khoan_id=tk.id,
            loai="thu",
            so_tien=gia_tl,
            doi_tac=None,
            ghi_chu=f"Thu thanh lý TSCĐ {tscd.ma_tscd}",
            source_app="ketoan",
            source_doc_id=f"tscd_thanh_ly_{tscd.id}",
            created_by=by_user,
        )
        db.add(gd)
        db.flush()

        # Auto-write sổ quỹ thu (phân loại CF: khac)
        sq = SoQuy(
            ngay=ngay,
            loai="thu",
            so_tien=gia_tl,
            tai_khoan=tk.ten_tk,
            noi_dung=f"Thanh lý TSCĐ {tscd.ma_tscd}",
            phan_loai_cf="khac",
            lien_quan="tscd",
            ref_id=str(tscd.id),
            created_by=by_user,
        )
        db.add(sq)
        db.flush()

    je = post_journal(
        db,
        ngay=ngay,
        mo_ta=(
            f"Thanh lý TSCĐ {tscd.ma_tscd} — {tscd.ten_tscd} "
            f"(thu {gia_tl:,.0f} đ, "
            f"{'lãi' if lai_lo > 0 else 'lỗ' if lai_lo < 0 else 'hoà vốn'} "
            f"{abs(lai_lo):,.0f} đ)"
        ),
        source_type="thanh_ly_tscd",
        source_id=str(tscd.id),
        by_user=by_user,
        lines=lines,
    )

    # Update TSCĐ
    tscd.trang_thai = "da_thanh_ly"
    tscd.ngay_thanh_ly = ngay
    tscd.gia_thanh_ly = gia_tl
    if ghi_chu:
        existing_note = (tscd.ghi_chu or "").rstrip()
        suffix = f"[Thanh lý {ngay.isoformat()}] {ghi_chu}"
        tscd.ghi_chu = f"{existing_note}\n{suffix}".strip()
    db.flush()
    return je
