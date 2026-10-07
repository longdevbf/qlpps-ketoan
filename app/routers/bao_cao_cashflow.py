"""Báo Cáo Lưu Chuyển Tiền Tệ (Cashflow Statement) — trong khoảng kỳ.

Endpoint: GET /api/bao-cao/cashflow?from=YYYY-MM-DD&to=YYYY-MM-DD

Trả 3 nhóm dòng tiền (dựa trên `ketoan.so_quy`), mã số theo mẫu B03:
  I.  HĐ Kinh Doanh (operating): Thu KH (01) - Trả NCC / Ads (02) - Trả lương (03) - Trả lãi vay (04)
      - Nộp thuế TNDN (05) + Thu khác (06) - Chi khác (07)
  II. HĐ Đầu Tư (investing): Mua CCDC / Sửa chữa lớn (21) + Thanh lý TSCĐ (22) - Cho vay (23)
      + Thu hồi cho vay (24) - Góp vốn (25) + Thu hồi góp vốn (26) + Thu lãi, cổ tức (27)
  III.HĐ Tài Chính (financing): Nhận vốn góp (31) - Trả vốn góp (32) + Vay NH (33)
      - Trả nợ gốc / lãi vay (34) - Trả gốc thuê TC (35) - Chia cổ tức (36)

  Các mã dòng tiền (so_quy.phan_loai_cf) khai ở MỘT bảng: app/services/phan_loai_cf.py. Khoản mục
  mới (04, 05, 06, 22-27, 31, 32, 35, 36) đọc thẳng phan_loai_cf — KHÔNG heuristic; heuristic chỉ còn
  cho dòng cũ phan_loai_cf IS NULL (giữ nguyên số báo cáo của dữ liệu cũ). Xem `_B03_MOI` bên dưới.

  Net Cashflow = I + II + III
  Số dư đầu kỳ + Net = Số dư cuối kỳ (phải khớp Cân Đối tại date=to)

Bonus:
  - daily breakdown (line chart)
  - by_account breakdown (bar chart)
  - top 5 transactions per nhóm phụ
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, func, or_, select, text
from sqlalchemy.orm import Session

from shared.auth import JWTPayload
from shared.db import get_db

from ..models import ChiPhiPhatSinh, SoDuDauKy, SoQuy, TaiKhoanNH
from ..services.phan_loai_cf import KHOA_HOP_LE
from ..services.so_quy_auto import so_du_truoc_ngay
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def _resolve_range(tu: Optional[date], den: Optional[date]) -> tuple[date, date]:
    """Default = current month (1 → today)."""
    today = date.today()
    if not den:
        den = today
    if not tu:
        tu = today.replace(day=1)
    return tu, den


def _f(x: Any) -> float:
    """Decimal/None safe → float."""
    if x is None:
        return 0.0
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _row(r: SoQuy) -> dict[str, Any]:
    """Serialize 1 SoQuy thành item dict (top-K transactions)."""
    return {
        "id": r.id,
        "ngay": r.ngay.isoformat() if r.ngay else None,
        "so_tien": _f(r.so_tien),
        "tai_khoan": r.tai_khoan,
        "lien_quan": r.lien_quan,
        "noi_dung": r.noi_dung,
        "ghi_chu": r.ghi_chu,
    }


# ── Tag detection (so_quy không có loai_chi_phi_id, dùng lien_quan + ghi_chu/noi_dung) ──

# Lower-case substrings hint
# BỎ token trần "kh" (2 ký tự) — ILIKE '%kh%' bắt nhầm 'khoan_vay','khau_hao'... vào
# Thu KH (dòng tiền hoạt động) thay vì tài chính. Dùng token có ranh giới. (L4, 2026-08-31)
_LIEN_QUAN_KH = ("khach", "phai_thu", "doanh_thu", "order", "don_hang", "cong_no")
_LIEN_QUAN_NCC = ("ncc", "mua_hang", "phai_tra", "cong_no")
_LIEN_QUAN_LUONG = ("luong", "payroll", "hcns")
_LIEN_QUAN_ADS = ("ads", "marketing", "mkt", "fb", "facebook", "google")
_LIEN_QUAN_CCDC = ("ccdc", "tai_san", "tscd", "asset")
_LIEN_QUAN_SUACHUA = ("sua_chua", "suachua", "repair", "bao_tri")
_LIEN_QUAN_VAY = ("vay", "loan", "tin_dung")
_LIEN_QUAN_NO_NH = ("lai_vay", "no_nh", "tra_no", "tra_lai")


def _ilike_any(col, keywords: tuple[str, ...]):
    """OR(col ILIKE %kw%) for each keyword."""
    return or_(*[col.ilike(f"%{kw}%") for kw in keywords])


def _khong_noi_bo():
    """Dòng KHÔNG phải chuyển nội bộ giữa hai quỹ. Phải NULL-safe: `~(NULL ILIKE ...)` là NULL nên
    nếu thiếu `IS NULL` thì dòng không có lien_quan bị bỏ nhầm khỏi báo cáo."""
    return or_(SoQuy.lien_quan.is_(None), ~SoQuy.lien_quan.ilike("chuyen_noi_bo"))


def _khong_lien_ket_vay():
    """Dòng KHÔNG gắn khoản vay (lien_quan 'vay_<id>' đã được khoan_vay_giao_dich đếm ở mã 33/34).
    NULL-safe như `_khong_noi_bo`."""
    return or_(SoQuy.lien_quan.is_(None), ~SoQuy.lien_quan.ilike("vay\\_%", escape="\\"))


# ════════════════════════════════════════════════════════════════════════════
# Group queries (sum + items top 5)
# ════════════════════════════════════════════════════════════════════════════

def _sum_items(
    db: Session,
    base_filters: list,
    *,
    top_k: int = 5,
    offset: int = 0,
) -> dict[str, Any]:
    """Trả {total, so_dong, items}.

    `top_k`/`offset` để popup "nguồn gốc con số" lật trang trên CHÍNH bộ lọc đã tính
    `total` — không có câu truy vấn thứ hai nào để lệch. `total` và `so_dong` luôn
    tính trên toàn bộ tập khớp, không theo trang.
    """
    tt = db.execute(
        select(func.coalesce(func.sum(SoQuy.so_tien), 0), func.count())
        .where(and_(*base_filters))
    ).first()
    total, so_dong = (tt[0] or Decimal("0"), int(tt[1] or 0)) if tt else (Decimal("0"), 0)

    rows = db.execute(
        select(SoQuy)
        .where(and_(*base_filters))
        .order_by(SoQuy.so_tien.desc(), SoQuy.ngay.desc())
        .offset(max(0, offset))
        .limit(top_k)
    ).scalars().all()

    return {"total": _f(total), "so_dong": so_dong, "items": [_row(r) for r in rows]}


def _by_cf_or_heuristic(
    cf_value: str,
    heuristic_filter,
):
    """Nếu phan_loai_cf đã set → dùng nó (ưu tiên); nếu NULL → fallback heuristic.

    Đảm bảo data cũ (chưa migrate) vẫn ra kết quả; data mới ghi đúng enum.
    """
    return or_(
        SoQuy.phan_loai_cf == cf_value,
        and_(SoQuy.phan_loai_cf.is_(None), heuristic_filter),
    )


def _operating_thu_kh(db: Session, tu: date, den: date, *, top_k: int = 5, offset: int = 0) -> dict[str, Any]:
    """Thu từ KH — ưu tiên phan_loai_cf='thu_kh', fallback heuristic.

    LOẠI TRỪ giải ngân vay (lien_quan='vay_<id>') khỏi heuristic.
    """
    return _sum_items(db, [
        SoQuy.loai == "thu",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
        _by_cf_or_heuristic("thu_kh", and_(
            ~SoQuy.lien_quan.ilike("vay\\_%", escape="\\"),
            or_(
                _ilike_any(SoQuy.lien_quan, _LIEN_QUAN_KH),
                _ilike_any(SoQuy.noi_dung, ("khách", "khach", "đơn", "don_hang")),
            ),
        )),
    ], top_k=top_k, offset=offset)


def _operating_tra_ncc(db: Session, tu: date, den: date, *, top_k: int = 5, offset: int = 0) -> dict[str, Any]:
    return _sum_items(db, [
        SoQuy.loai == "chi",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
        _by_cf_or_heuristic("tra_ncc", _ilike_any(SoQuy.lien_quan, _LIEN_QUAN_NCC)),
    ], top_k=top_k, offset=offset)


def _operating_tra_ads(db: Session, tu: date, den: date, *, top_k: int = 5, offset: int = 0) -> dict[str, Any]:
    return _sum_items(db, [
        SoQuy.loai == "chi",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
        _by_cf_or_heuristic("nap_ads", or_(
            _ilike_any(SoQuy.lien_quan, _LIEN_QUAN_ADS),
            _ilike_any(SoQuy.ghi_chu, ("ads", "marketing", "facebook", "google")),
            _ilike_any(SoQuy.noi_dung, ("ads", "marketing", "facebook", "google")),
        )),
    ], top_k=top_k, offset=offset)


def _operating_tra_luong(db: Session, tu: date, den: date, *, top_k: int = 5, offset: int = 0) -> dict[str, Any]:
    return _sum_items(db, [
        SoQuy.loai == "chi",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
        _by_cf_or_heuristic("tra_luong", or_(
            _ilike_any(SoQuy.lien_quan, _LIEN_QUAN_LUONG),
            _ilike_any(SoQuy.ghi_chu, ("lương", "luong", "salary", "payroll")),
            _ilike_any(SoQuy.noi_dung, ("lương", "luong", "salary", "payroll")),
        )),
    ], top_k=top_k, offset=offset)


def _investing_mua_ccdc(db: Session, tu: date, den: date, *, top_k: int = 5, offset: int = 0) -> dict[str, Any]:
    return _sum_items(db, [
        SoQuy.loai == "chi",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
        _by_cf_or_heuristic("mua_ccdc", or_(
            _ilike_any(SoQuy.lien_quan, _LIEN_QUAN_CCDC),
            _ilike_any(SoQuy.ghi_chu, ("ccdc", "tài sản", "tai san", "tscd")),
        )),
    ], top_k=top_k, offset=offset)


def _investing_sua_chua(db: Session, tu: date, den: date, *, top_k: int = 5, offset: int = 0) -> dict[str, Any]:
    return _sum_items(db, [
        SoQuy.loai == "chi",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
        _by_cf_or_heuristic("sua_chua_lon", or_(
            _ilike_any(SoQuy.lien_quan, _LIEN_QUAN_SUACHUA),
            _ilike_any(SoQuy.ghi_chu, ("sửa chữa", "sua chua", "bảo trì", "bao tri")),
        )),
    ], top_k=top_k, offset=offset)


def _financing_from_kvgd(
    db: Session, tu: date, den: date, loai_list: tuple[str, ...],
    *, top_k: int = 5, offset: int = 0,
) -> dict[str, Any]:
    """Đọc giao dịch khoản vay từ `ketoan.khoan_vay_giao_dich` — SOURCE OF TRUTH
    cho hoạt động tài chính (giải ngân / trả gốc / trả lãi / đáo hạn).

    LCTT là báo cáo THEO PHƯƠNG PHÁP TRỰC TIẾP (chỉ ghi nhận tiền THỰC SỰ ra/vào
    quỹ) nên chỉ đếm các giao dịch khoản vay có bút toán tiền thật đi kèm — tức
    `ref_so_quy_id` phải trỏ tới 1 dòng `so_quy` còn tồn tại (INNER JOIN). Một
    giao dịch có `ref_so_quy_id` mồ côi (dòng `so_quy` gốc đã bị xoá — ví dụ
    khoản vay đã tất toán rồi bị dọn sổ quỹ nhưng chưa xoá `khoan_vay_giao_dich`
    tương ứng) KHÔNG được tính vào dòng tiền, nếu không "Trả nợ gốc, lãi vay"
    (mã 34) sẽ bị thổi phồng bằng những khoản tiền chưa từng thực xuất quỹ, kéo
    theo Lưu chuyển tiền thuần trong kỳ (mã 50) và Tiền cuối kỳ (mã 70) bị lệch
    hàng trăm triệu so với số dư quỹ thật (đối chiếu qua `_by_account`).
    """
    from sqlalchemy import text as _t
    placeholders = ",".join(f"'{l}'" for l in loai_list)
    sql = f"""
        SELECT g.id, g.ngay, g.loai, g.so_tien, kv.ma_khoan, kv.nguon_vay,
               g.ghi_chu
        FROM ketoan.khoan_vay_giao_dich g
        JOIN ketoan.khoan_vay kv ON kv.id = g.khoan_vay_id
        JOIN ketoan.so_quy sq ON sq.id = g.ref_so_quy_id
        WHERE g.loai IN ({placeholders})
          AND g.ngay BETWEEN :tu AND :den
        ORDER BY g.so_tien DESC, g.ngay DESC
    """
    try:
        rows = db.execute(_t(sql), {"tu": tu, "den": den}).mappings().all()
    except Exception:
        db.rollback()
        return {"total": 0.0, "so_dong": 0, "items": []}
    total = sum(_f(r["so_tien"]) for r in rows)
    items = [
        {
            "id": r["id"],
            "ngay": r["ngay"].isoformat() if r["ngay"] else None,
            "so_tien": _f(r["so_tien"]),
            "tai_khoan": None,
            "lien_quan": r["ma_khoan"],
            "noi_dung": f"[{r['loai']}] {r['nguon_vay']}",
            "ghi_chu": r.get("ghi_chu"),
        }
        for r in rows[max(0, offset): max(0, offset) + top_k]
    ]
    return {"total": total, "so_dong": len(rows), "items": items}


def _financing_vay(db: Session, tu: date, den: date,
                   *, top_k: int = 5, offset: int = 0) -> dict[str, Any]:
    """Vay nhận về (Thu) = giải ngân từ khoan_vay_giao_dich + so_quy manual.

    Tránh double count với so_quy đã auto-link (lien_quan='vay_<kvgd.id>').
    """
    kvgd = _financing_from_kvgd(db, tu, den, ("giai_ngan",))
    sq = _sum_items(db, [
        SoQuy.loai == "thu",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
        SoQuy.phan_loai_cf == "vay_nh",
        _khong_lien_ket_vay(),   # NULL-safe (trước: ~ilike → dòng không có lien_quan biến mất khỏi mã 33)
    ])
    gop = kvgd["items"] + sq["items"]
    return {
        "total": kvgd["total"] + sq["total"],
        "so_dong": kvgd.get("so_dong", len(kvgd["items"])) + sq.get("so_dong", len(sq["items"])),
        "items": gop[max(0, offset): max(0, offset) + top_k],
    }


def _financing_tra_no(db: Session, tu: date, den: date,
                      *, top_k: int = 5, offset: int = 0) -> dict[str, Any]:
    """Trả gốc + lãi (Chi) = trả nợ từ khoan_vay_giao_dich + so_quy manual."""
    kvgd = _financing_from_kvgd(db, tu, den, ("tra_goc", "tra_lai", "tra_goc_lai", "dao_han"))
    sq = _sum_items(db, [
        SoQuy.loai == "chi",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
        SoQuy.phan_loai_cf == "tra_nh",
        _khong_lien_ket_vay(),   # NULL-safe (trước: ~ilike → dòng không có lien_quan biến mất khỏi mã 34 VÀ khỏi chi_khac)
    ])
    gop = kvgd["items"] + sq["items"]
    return {
        "total": kvgd["total"] + sq["total"],
        "so_dong": kvgd.get("so_dong", len(kvgd["items"])) + sq.get("so_dong", len(sq["items"])),
        "items": gop[max(0, offset): max(0, offset) + top_k],
    }


# Khoản mục B03 MỚI (01/10/2026). Mỗi dòng: (nhóm trong JSON, khoá JSON, loai so_quy, phan_loai_cf, bộ lọc thêm).
# - Đọc thẳng `phan_loai_cf == khoá`, KHÔNG heuristic — cùng predicate cho cả "hiển thị" lẫn "loại khỏi chi_khac"
#   (bài học DUP-02 ở _full_chi_classified_ids: lệch hai bên thì dòng biến mất hoặc bị đếm đôi).
# - Khoá JSON `thu_khac` = mã 06: phiếu THU mang khoá 'khac' (khoá cũ dùng cả hai chiều) mà không phải chuyển nội bộ.
# - `tra_lai_vay` thủ công chỉ tính dòng KHÔNG có lien_quan 'vay_<id>' (như tra_nh/vay_nh) để khỏi đếm đôi với
#   khoan_vay_giao_dich — lãi vay tự sinh từ Khoản vay vẫn nằm ở mã 34 (giữ nguyên số cũ).
_B03_MOI = (
    ("operating", "tra_lai_vay", "chi", "tra_lai_vay", _khong_lien_ket_vay),          # 04
    ("operating", "nop_thue_tndn", "chi", "nop_thue_tndn", None),                    # 05
    ("operating", "thu_khac", "thu", "khac", _khong_noi_bo),                          # 06
    ("investing", "thanh_ly_tscd", "thu", "thanh_ly_tscd", None),                    # 22
    ("investing", "chi_cho_vay", "chi", "chi_cho_vay", None),                        # 23
    ("investing", "thu_hoi_cho_vay", "thu", "thu_hoi_cho_vay", None),                # 24
    ("investing", "chi_gop_von", "chi", "chi_gop_von", None),                        # 25
    ("investing", "thu_hoi_gop_von", "thu", "thu_hoi_gop_von", None),                # 26
    ("investing", "thu_lai", "thu", "thu_lai", None),                                # 27
    ("financing", "nhan_von", "thu", "nhan_von", None),                              # 31
    ("financing", "tra_von", "chi", "tra_von", None),                                # 32
    ("financing", "tra_goc_thue_tc", "chi", "tra_goc_thue_tc", None),                # 35
    ("financing", "chia_co_tuc", "chi", "chia_co_tuc", None),                        # 36
)
# Lệch bảng mã (gõ sai khoá / bỏ khoá khỏi app/services/phan_loai_cf.py) thì dừng ngay lúc nạp module.
assert {_row_[3] for _row_ in _B03_MOI} <= set(KHOA_HOP_LE), "bảng _B03_MOI có phan_loai_cf không có trong phan_loai_cf.py"


def _b03_moi(db: Session, tu: date, den: date, loai: str, cf: str, loc=None,
             *, top_k: int = 5, offset: int = 0) -> dict[str, Any]:
    """Một khoản mục B03 mới = so_quy.loai + phan_loai_cf == cf (+ bộ lọc thêm) trong kỳ."""
    filters = [SoQuy.loai == loai, SoQuy.ngay >= tu, SoQuy.ngay <= den, SoQuy.phan_loai_cf == cf]
    if loc is not None:
        filters.append(loc())
    return _sum_items(db, filters, top_k=top_k, offset=offset)


def _operating_chi_khac(
    db: Session,
    tu: date,
    den: date,
    excl_ids: set[int],
    *,
    top_k: int = 5,
    offset: int = 0,
) -> dict[str, Any]:
    """Chi khác (mã 07) = chi trong kỳ KHÔNG thuộc nhóm nào đã phân loại (NCC/Ads/Lương/Đầu tư/Tài chính/
    khoản mục B03 mới/chuyển nội bộ) — `excl_ids` do `_full_chi_classified_ids` dựng."""
    base_filters = [
        SoQuy.loai == "chi",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
    ]
    if excl_ids:
        base_filters.append(~SoQuy.id.in_(excl_ids))

    return _sum_items(db, base_filters, top_k=top_k, offset=offset)


# ════════════════════════════════════════════════════════════════════════════
# Daily + by_account
# ════════════════════════════════════════════════════════════════════════════

def _daily_breakdown(db: Session, tu: date, den: date) -> list[dict[str, Any]]:
    """Group SoQuy theo `ngay` → list[{ngay, thu, chi, net}] full date range (zero-fill)."""
    rows = db.execute(
        select(
            SoQuy.ngay,
            func.coalesce(func.sum(
                case((SoQuy.loai == "thu", SoQuy.so_tien), else_=0)
            ), 0),
            func.coalesce(func.sum(
                case((SoQuy.loai == "chi", SoQuy.so_tien), else_=0)
            ), 0),
        )
        .where(SoQuy.ngay >= tu, SoQuy.ngay <= den)
        .group_by(SoQuy.ngay)
    ).all()

    by_day: dict[date, tuple[float, float]] = {}
    for ngay, thu, chi in rows:
        by_day[ngay] = (_f(thu), _f(chi))

    out: list[dict[str, Any]] = []
    n_days = (den - tu).days + 1
    for i in range(n_days):
        d = tu + timedelta(days=i)
        thu, chi = by_day.get(d, (0.0, 0.0))
        out.append({
            "ngay": d.isoformat(),
            "thu": thu,
            "chi": chi,
            "net": thu - chi,
        })
    return out


def _by_account(db: Session, tu: date, den: date) -> list[dict[str, Any]]:
    """Per TaiKhoanNH: thu/chi trong kỳ + so_du_cuoi tại `den` (snapshot SoDuDauKy + Σ(thu-chi) từ snapshot)."""
    tks = db.execute(
        select(TaiKhoanNH.id, TaiKhoanNH.ten_tk, TaiKhoanNH.so_du_dau, TaiKhoanNH.loai)
        .where(TaiKhoanNH.active.is_(True))
        .order_by(TaiKhoanNH.ten_tk)
    ).all()

    out: list[dict[str, Any]] = []
    for tk in tks:
        thu_in = db.scalar(
            select(func.coalesce(func.sum(SoQuy.so_tien), 0)).where(
                SoQuy.tai_khoan == tk.ten_tk,
                SoQuy.loai == "thu",
                SoQuy.ngay >= tu, SoQuy.ngay <= den,
            )
        ) or Decimal("0")
        chi_in = db.scalar(
            select(func.coalesce(func.sum(SoQuy.so_tien), 0)).where(
                SoQuy.tai_khoan == tk.ten_tk,
                SoQuy.loai == "chi",
                SoQuy.ngay >= tu, SoQuy.ngay <= den,
            )
        ) or Decimal("0")
        # Số dư cuối tài khoản tại hết ngày `den` = số dư NGAY TRƯỚC ngày `den`+1 theo thuật toán neo
        # SoDuDauKy dùng chung (so_quy_auto.so_du_truoc_ngay — màn Sổ quỹ / Ngân hàng / mã 60 / cân đối).
        # Trước đây bỏ qua snapshot (so_du_dau + MỌI giao dịch) → cột "Số dư cuối" cộng 1,36 tỷ
        # trong khi mã 70 = 97 triệu (QA 25/09/2026, kỳ 09/2026).
        so_du_cuoi = _f(so_du_truoc_ngay(db, tk.id, tk.ten_tk, den + timedelta(days=1)))

        # Chuyển nội bộ giữa 2 TK (cùng predicate loại khỏi B03 ở _full_chi_classified_ids) —
        # trả riêng để màn LCTT ghi rõ vì sao Σ thu/chi theo tài khoản > tổng thu/chi B03.
        noi_bo = or_(SoQuy.lien_quan.ilike("chuyen_noi_bo"), SoQuy.phan_loai_cf == "noi_bo")
        thu_nb, chi_nb = (db.scalar(
            select(func.coalesce(func.sum(SoQuy.so_tien), 0)).where(
                SoQuy.tai_khoan == tk.ten_tk, SoQuy.loai == lo, SoQuy.ngay >= tu, SoQuy.ngay <= den, noi_bo,
            )
        ) or Decimal("0") for lo in ("thu", "chi"))

        thu_f, chi_f = _f(thu_in), _f(chi_in)
        out.append({
            "ten_tk": tk.ten_tk,
            "loai": tk.loai,
            "thu": thu_f,
            "chi": chi_f,
            "net": thu_f - chi_f,
            "thu_noi_bo": _f(thu_nb),
            "chi_noi_bo": _f(chi_nb),
            "so_du_cuoi": so_du_cuoi,
        })
    return out


def _so_du_dau_ky(db: Session, tu: date) -> float:
    """Tổng số dư các tài khoản tiền NGAY TRƯỚC ngày `tu` (mã 60).

    Dùng đúng thuật toán neo SoDuDauKy của màn Sổ quỹ / Ngân hàng
    (so_quy_auto.so_du_truoc_ngay: neo lùi → neo tiến → so_du_dau + toàn bộ giao dịch)
    để "Tiền đầu kỳ" LCTT = tồn đầu kỳ Sổ quỹ = số dư tiền trên Cân đối ngày `tu`−1.
    """
    tks = db.execute(
        select(TaiKhoanNH.id, TaiKhoanNH.ten_tk)
        .where(TaiKhoanNH.active.is_(True))
    ).all()
    return _f(sum((so_du_truoc_ngay(db, tk.id, tk.ten_tk, tu) for tk in tks), Decimal("0")))


def _canh_bao_dau_ky(db: Session, tu: date) -> Optional[str]:
    """Cảnh báo khi kỳ xem bắt đầu TRƯỚC mốc số dư đầu kỳ sớm nhất đã khai.

    Vì sao cần (đo trên production 05/10/2026): `so_du_dau_ky` chỉ có 4 dòng, đều ở
    01/05/2026. Xem từ trước mốc đó thì `so_du_truoc_ngay` phải suy NGƯỢC = neo 01/05
    trừ các phiếu tháng 4 — mà tháng 4 chỉ có 6 phiếu, cả 6 đều nhập bù trong tháng 5
    (18→27/05), trong đó 4 phiếu là giải ngân vay do hệ thống TỰ sinh khi khai khoản
    vay cũ, luôn ghi vào quỹ Tiền Mặt. Tiền vay 1.485.714.292đ vào sổ nhưng khoản chi
    tương ứng của tháng 4 chưa ai nhập → quỹ Tiền Mặt đầu kỳ ra −1.336.813.744đ.

    Chọn CẢNH BÁO chứ không sửa số: số đang hiển thị đúng với dữ liệu đang có, sửa
    thầm sẽ giấu mất chuyện tháng 4 ghi thiếu. Kỳ bắt đầu từ 01/05 trở đi vẫn đúng
    (đầu kỳ = 119.934.370đ = tổng 4 mốc đã khai).
    """
    moc = db.execute(
        select(func.min(SoDuDauKy.thang))
    ).scalar()
    if moc is None or tu >= moc:
        return None
    return (
        f"Sổ quỹ chỉ khai số dư đầu kỳ từ {moc.strftime('%d/%m/%Y')}. Kỳ này bắt đầu "
        f"trước mốc đó nên 'Tiền đầu kỳ' là số suy ngược, không phải số kiểm quỹ — "
        f"giai đoạn trước mốc chưa nhập đủ phiếu."
    )


# ════════════════════════════════════════════════════════════════════════════
# Endpoint
# ════════════════════════════════════════════════════════════════════════════

@router.get("/cashflow")
def bao_cao_cashflow(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = Query(None),
):
    """Báo cáo lưu chuyển tiền tệ trong [from, to]. Default = tháng hiện tại."""
    tu, den = _resolve_range(from_, to)

    # ── Operating ───────────────────────────────────────────────────────────
    thu_kh = _operating_thu_kh(db, tu, den)
    tra_ncc = _operating_tra_ncc(db, tu, den)
    tra_ads = _operating_tra_ads(db, tu, den)
    tra_luong = _operating_tra_luong(db, tu, den)

    # ── Investing ───────────────────────────────────────────────────────────
    mua_ccdc = _investing_mua_ccdc(db, tu, den)
    sua_chua = _investing_sua_chua(db, tu, den)

    # ── Financing ───────────────────────────────────────────────────────────
    vay_nh = _financing_vay(db, tu, den)
    tra_no_nh = _financing_tra_no(db, tu, den)

    # ── Khoản mục B03 MỚI: đọc thẳng phan_loai_cf (xem _B03_MOI) ─────────────
    moi: dict[str, dict[str, Any]] = {"operating": {}, "investing": {}, "financing": {}}
    net_moi = {"operating": 0.0, "investing": 0.0, "financing": 0.0}
    for nhom, khoa, loai, cf, loc in _B03_MOI:
        grp = _b03_moi(db, tu, den, loai, cf, loc)
        moi[nhom][khoa] = grp
        net_moi[nhom] += grp["total"] if loai == "thu" else -grp["total"]

    # ── Chi khác (operating) = chi trong kỳ NOT IN các nhóm chi trên ────────
    # Build excl_ids = mọi id chi đã phân loại (NCC/Ads/Lương/CCDC/SửaChữa/TrảNợ)
    classified_chi_ids = set()
    for grp in (tra_ncc, tra_ads, tra_luong, mua_ccdc, sua_chua, tra_no_nh):
        for it in grp["items"]:
            classified_chi_ids.add(it["id"])
    # Cũng cần fetch FULL classified ids (không chỉ top-5). Re-query ids từng nhóm.
    full_classified_ids = _full_chi_classified_ids(db, tu, den)
    chi_khac = _operating_chi_khac(db, tu, den, full_classified_ids)

    net_operating = (
        thu_kh["total"]
        - tra_ncc["total"] - tra_ads["total"]
        - tra_luong["total"] - chi_khac["total"]
        + net_moi["operating"]
    )
    net_investing = -(mua_ccdc["total"] + sua_chua["total"]) + net_moi["investing"]
    net_financing = vay_nh["total"] - tra_no_nh["total"] + net_moi["financing"]
    net_cashflow = net_operating + net_investing + net_financing

    so_du_dau = _so_du_dau_ky(db, tu)
    so_du_cuoi = so_du_dau + net_cashflow

    daily = _daily_breakdown(db, tu, den)
    by_acc = _by_account(db, tu, den)

    return {
        "ok": True,
        "from": tu.isoformat(),
        "to": den.isoformat(),
        "n_days": (den - tu).days + 1,
        "so_du_dau_ky": so_du_dau,
        "canh_bao_dau_ky": _canh_bao_dau_ky(db, tu),
        "operating": {
            "thu_kh": thu_kh,
            "tra_ncc": tra_ncc,
            "tra_ads": tra_ads,
            "tra_luong": tra_luong,
            **moi["operating"],  # tra_lai_vay (04), nop_thue_tndn (05), thu_khac (06)
            "chi_khac": chi_khac,
            "net": net_operating,
        },
        "investing": {
            "mua_ccdc": mua_ccdc,
            "sua_chua": sua_chua,
            **moi["investing"],  # thanh_ly_tscd (22) … thu_lai (27)
            "net": net_investing,
        },
        "financing": {
            "vay_nh": vay_nh,
            "tra_no_nh": tra_no_nh,
            **moi["financing"],  # nhan_von (31), tra_von (32), tra_goc_thue_tc (35), chia_co_tuc (36)
            "net": net_financing,
        },
        "net_cashflow": net_cashflow,
        "so_du_cuoi_ky": so_du_cuoi,
        "daily": daily,
        "by_account": by_acc,
    }


def _full_chi_classified_ids(db: Session, tu: date, den: date) -> set[int]:
    """Lấy đầy đủ ID các so_quy chi đã thuộc nhóm phân loại (NCC/Ads/Lương/CCDC/SửaChữa/TrảNợ/khoá chi B03 mới).

    Dùng để loại trừ khỏi `chi_khac`.
    """
    ids: set[int] = set()
    base = [
        SoQuy.loai == "chi",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
    ]
    # DUP-02 + L3 (2026-08-31): tập loại-trừ phải KHỚP CHÍNH XÁC predicate hiển thị →
    # dùng chung `_by_cf_or_heuristic(cf, heuristic)` = or_(phan_loai_cf==cf,
    # and_(phan_loai_cf IS NULL, heuristic)). Nếu chỉ or_(cf, heuristic) như trước thì
    # chi có phan_loai_cf='khac' + keyword bị LOẠI khỏi chi_khac NHƯNG không vào bucket
    # nào → BIẾN MẤT khỏi báo cáo (net sai). Dùng helper là khít cả 2 chiều.
    _preds = [
        _by_cf_or_heuristic("tra_ncc", _ilike_any(SoQuy.lien_quan, _LIEN_QUAN_NCC)),
        _by_cf_or_heuristic("nap_ads", or_(
            _ilike_any(SoQuy.lien_quan, _LIEN_QUAN_ADS),
            _ilike_any(SoQuy.ghi_chu, ("ads", "marketing", "facebook", "google")),
            _ilike_any(SoQuy.noi_dung, ("ads", "marketing", "facebook", "google")),
        )),
        _by_cf_or_heuristic("tra_luong", or_(
            _ilike_any(SoQuy.lien_quan, _LIEN_QUAN_LUONG),
            _ilike_any(SoQuy.ghi_chu, ("lương", "luong", "salary", "payroll")),
            _ilike_any(SoQuy.noi_dung, ("lương", "luong", "salary", "payroll")),
        )),
        _by_cf_or_heuristic("mua_ccdc", or_(
            _ilike_any(SoQuy.lien_quan, _LIEN_QUAN_CCDC),
            _ilike_any(SoQuy.ghi_chu, ("ccdc", "tài sản", "tai san", "tscd")),
        )),
        _by_cf_or_heuristic("sua_chua_lon", or_(
            _ilike_any(SoQuy.lien_quan, _LIEN_QUAN_SUACHUA),
            _ilike_any(SoQuy.ghi_chu, ("sửa chữa", "sua chua", "bảo trì", "bao tri")),
        )),
        _by_cf_or_heuristic("tra_nh", or_(
            _ilike_any(SoQuy.lien_quan, _LIEN_QUAN_NO_NH),
            _ilike_any(SoQuy.ghi_chu, ("lãi vay", "lai vay", "trả nợ", "tra no", "nợ ngân hàng")),
        )),
    ]
    for _p in _preds:
        rs = db.execute(select(SoQuy.id).where(*base, _p)).scalars().all()
        ids.update(rs)
    # Khoá chi MỚI (01/10/2026): phan_loai_cf == khoá, không heuristic. KHÔNG kèm bộ lọc vay_<id> của mã 04
    # (giống tra_nh ở trên): dòng vay_<id> bị loại khỏi chi_khac, phần tiền đó do khoan_vay_giao_dich đếm ở mã 34.
    cf_chi_moi = [cf for (_n, _k, lo, cf, _l) in _B03_MOI if lo == "chi"]
    rs = db.execute(select(SoQuy.id).where(*base, SoQuy.phan_loai_cf.in_(cf_chi_moi))).scalars().all()
    ids.update(rs)
    # Chuyển nội bộ (luân chuyển quỹ giữa 2 TK) — KHÔNG phải chi phí, chỉ là
    # dịch chuyển tiền nội bộ. Loại khỏi chi_khac (2026-06-20). Dòng 'thu' đối
    # ứng vốn đã không lọt vào thu_kh (heuristic KH), nên loại nốt chi → net 0.
    rs = db.execute(
        select(SoQuy.id).where(
            *base,
            or_(
                SoQuy.lien_quan.ilike("chuyen_noi_bo"),
                SoQuy.phan_loai_cf == "noi_bo",
            ),
        )
    ).scalars().all()
    ids.update(rs)
    return ids


# ════════════════════════════════════════════════════════════════════════════
# CÔNG NỢ NGẦM — accrual vs cash đối chiếu
# ════════════════════════════════════════════════════════════════════════════

@router.get("/cong-no-ngam")
def get_cong_no_ngam(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu: Annotated[Optional[date], Query(alias="from")] = None,
    den: Annotated[Optional[date], Query(alias="to")] = None,
):
    """So sánh chi phí PHÁT SINH (accrual) vs ĐÃ TRẢ (cash) trong kỳ.

    4 nhóm chính:
    - **Ads**: marketing.ads_cost (accrual) vs so_quy.phan_loai_cf='nap_ads' (cash)
    - **Lương**: hcns.payroll.luong_thuc_linh (accrual) vs so_quy='tra_luong' (cash)
    - **NCC**: muahang.purchase_orders (accrual) vs so_quy='tra_ncc' (cash)
    - **Vay/Lãi**: ketoan.khoan_vay_giao_dich vs so_quy='vay_nh'/'tra_nh'

    Cảnh báo (warning) khi `con_no` > 0 cuối kỳ — công ty đang nợ ngầm.
    """
    from sqlalchemy import text as _t
    tu, den = _resolve_range(tu, den)
    p = {"tu": tu, "den": den, "thang_tu": tu.strftime("%Y-%m"), "thang_den": den.strftime("%Y-%m")}

    def _scalar(sql: str, params: dict | None = None) -> float:
        try:
            v = db.execute(_t(sql), params or p).scalar()
            return float(v or 0)
        except Exception:
            db.rollback()
            return 0.0

    # 1. Ads — accrual từ marketing.ads_cost (theo thang YYYY-MM)
    ads_phat_sinh = _scalar(
        "SELECT COALESCE(SUM(chi_phi),0) FROM marketing.ads_cost "
        "WHERE thang BETWEEN :thang_tu AND :thang_den"
    )
    # "Đã trả" = ĐÚNG khoản mục tương ứng của bảng B03 (/cashflow: phan_loai_cf hoặc heuristic khi
    # chưa phân loại) — trước đây chỉ đếm phan_loai_cf nên cùng trang LCTT: B03 "chi trả quảng cáo"
    # 10tr mà Công nợ ngầm "đã trả" 0; "chi trả người lao động" 146,9tr mà "đã trả" 0 (QA 25/09/2026).
    ads_da_tra = _operating_tra_ads(db, tu, den)["total"]

    # 2. Lương — accrual từ hcns.payroll
    luong_phat_sinh = _scalar(
        "SELECT COALESCE(SUM(luong_thuc_linh),0) FROM hcns.payroll "
        "WHERE thang BETWEEN :thang_tu AND :thang_den"
    )
    luong_da_tra = _operating_tra_luong(db, tu, den)["total"]

    # 3. NCC — accrual từ muahang.purchase_orders
    # PO có cột status; "đã ký/đã nhận" coi như phát sinh chi phí.
    ncc_phat_sinh = _scalar(
        """SELECT COALESCE(SUM((
              SELECT COALESCE(SUM(s.so_luong * s.don_gia), 0)
              FROM jsonb_array_elements(po.combos) c
              CROSS JOIN LATERAL jsonb_to_record(c) AS s(so_luong numeric, don_gia numeric)
            )), 0)
           FROM muahang.purchase_orders po
           WHERE po.created_at::date BETWEEN :tu AND :den
             AND po.status NOT IN ('Hủy','Chờ xác nhận')"""
    )
    # Nếu jsonb structure khác → fallback đơn giản hơn
    if not ncc_phat_sinh:
        ncc_phat_sinh = _scalar(
            "SELECT COALESCE(SUM((selected_ncc_id IS NOT NULL)::int * 0),0) FROM muahang.purchase_orders"
        )
    ncc_da_tra = _operating_tra_ncc(db, tu, den)["total"]

    # 4. Vay — vay/trả nợ
    vay_nhan = _financing_vay(db, tu, den)["total"]       # = mã 33 B03
    vay_tra = _financing_tra_no(db, tu, den)["total"]     # = mã 34 B03

    rows = [
        {
            "khoan": "Ads / Marketing",
            "phat_sinh": ads_phat_sinh,
            "da_tra": ads_da_tra,
            "con_no": ads_phat_sinh - ads_da_tra,
            "ghi_chu": "FB/Google đã chạy nhưng chưa nạp đủ" if ads_phat_sinh > ads_da_tra else None,
        },
        {
            "khoan": "Lương nhân viên",
            "phat_sinh": luong_phat_sinh,
            "da_tra": luong_da_tra,
            "con_no": luong_phat_sinh - luong_da_tra,
            "ghi_chu": "Lương đã hạch toán nhưng chưa chuyển khoản" if luong_phat_sinh > luong_da_tra else None,
        },
        {
            "khoan": "Mua hàng NCC",
            "phat_sinh": ncc_phat_sinh,
            "da_tra": ncc_da_tra,
            "con_no": ncc_phat_sinh - ncc_da_tra,
            "ghi_chu": "PO đã nhận nhưng chưa thanh toán" if ncc_phat_sinh > ncc_da_tra else None,
        },
        {
            "khoan": "Vay ngân hàng (net thu/chi)",
            "phat_sinh": vay_nhan,
            "da_tra": vay_tra,
            "con_no": vay_nhan - vay_tra,
            "ghi_chu": "Net vay > trả nợ" if vay_nhan > vay_tra else None,
        },
    ]

    tong_no = sum(r["con_no"] for r in rows[:3] if r["con_no"] > 0)  # exclude vay
    return {
        "from": tu.isoformat(),
        "to": den.isoformat(),
        "rows": rows,
        "tong_cong_no_ngam": tong_no,
        "warning": (
            f"⚠️ Đang nợ ngầm {tong_no:,.0f}đ — sức ép dòng tiền tương lai"
            if tong_no > 0 else None
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# CASHFLOW VALIDATION — Đối chiếu trực tiếp vs gián tiếp (TT200)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/cashflow-validation")
def get_cashflow_validation(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu: Annotated[Optional[date], Query(alias="from")] = None,
    den: Annotated[Optional[date], Query(alias="to")] = None,
):
    """Cross-check Net Cashflow trực tiếp vs gián tiếp (TT200).

    Phương pháp gián tiếp:
        Net CF (HĐKD)
          = LN sau thuế (P&L)
          + Khấu hao (chi phí không thoát tiền)
          + Tăng/giảm phải trả (NCC chưa thanh toán → cộng)
          - Tăng/giảm phải thu (KH chưa trả → trừ)
          - Tăng/giảm hàng tồn kho

    So với Net CF từ direct (operating section của /cashflow). Nếu lệch >5% →
    cảnh báo có giao dịch chưa hạch toán đúng.
    """
    from sqlalchemy import text as _t
    tu, den = _resolve_range(tu, den)
    p = {"tu": tu, "den": den, "thang_tu": tu.strftime("%Y-%m"), "thang_den": den.strftime("%Y-%m")}

    def _scalar(sql: str, params: dict | None = None) -> float:
        try:
            v = db.execute(_t(sql), params or p).scalar()
            return float(v or 0)
        except Exception:
            db.rollback()
            return 0.0

    # Direct = lấy từ cashflow operating
    thu_kh = _operating_thu_kh(db, tu, den)["total"]
    tra_ncc = _operating_tra_ncc(db, tu, den)["total"]
    tra_ads = _operating_tra_ads(db, tu, den)["total"]
    tra_luong = _operating_tra_luong(db, tu, den)["total"]
    direct_net_op = thu_kh - tra_ncc - tra_ads - tra_luong

    # Indirect components
    # (a) LN sau thuế ≈ doanh thu - chi phí phát sinh
    doanh_thu = _scalar(
        "SELECT COALESCE(SUM(so_tien),0) FROM ketoan.doanh_thu "
        "WHERE ngay BETWEEN :tu AND :den"
    )
    chi_phi = _scalar(
        "SELECT COALESCE(SUM(so_tien),0) FROM ketoan.chi_phi_phat_sinh "
        "WHERE ngay BETWEEN :tu AND :den"
    )
    chi_phi_co_dinh = _scalar(
        "SELECT COALESCE(SUM(so_tien),0) FROM ketoan.chi_phi_co_dinh "
        "WHERE thang BETWEEN :thang_tu AND :thang_den"
    )
    luong_phat_sinh = _scalar(
        "SELECT COALESCE(SUM(luong_thuc_linh),0) FROM hcns.payroll "
        "WHERE thang BETWEEN :thang_tu AND :thang_den"
    )
    ads_phat_sinh = _scalar(
        "SELECT COALESCE(SUM(chi_phi),0) FROM marketing.ads_cost "
        "WHERE thang BETWEEN :thang_tu AND :thang_den"
    )
    ln_sau_thue = doanh_thu - chi_phi - chi_phi_co_dinh - luong_phat_sinh - ads_phat_sinh

    # (b) Khấu hao — fail-soft (chưa có module khấu hao chuẩn)
    khau_hao = 0.0

    # (c) Biến động phải thu/phải trả — proxy: chênh accrual vs cash
    bien_dong_phai_thu = max(0.0, doanh_thu - thu_kh)  # KH chưa trả → tăng phải thu (trừ CF)
    bien_dong_phai_tra_ncc = max(0.0, chi_phi - tra_ncc)  # NCC chưa thanh toán → tăng phải trả (cộng CF)
    bien_dong_phai_tra_ads = max(0.0, ads_phat_sinh - tra_ads)
    bien_dong_phai_tra_luong = max(0.0, luong_phat_sinh - tra_luong)

    indirect_net_op = (
        ln_sau_thue
        + khau_hao
        + bien_dong_phai_tra_ncc
        + bien_dong_phai_tra_ads
        + bien_dong_phai_tra_luong
        - bien_dong_phai_thu
    )

    chenh_lech = direct_net_op - indirect_net_op
    pct_lech = (abs(chenh_lech) / max(abs(direct_net_op), 1)) * 100

    return {
        "from": tu.isoformat(),
        "to": den.isoformat(),
        "direct": {
            "thu_kh": thu_kh,
            "tra_ncc": tra_ncc,
            "tra_ads": tra_ads,
            "tra_luong": tra_luong,
            "net_operating": direct_net_op,
        },
        "indirect": {
            "ln_sau_thue": ln_sau_thue,
            "khau_hao": khau_hao,
            "bien_dong_phai_thu": bien_dong_phai_thu,
            "bien_dong_phai_tra_ncc": bien_dong_phai_tra_ncc,
            "bien_dong_phai_tra_ads": bien_dong_phai_tra_ads,
            "bien_dong_phai_tra_luong": bien_dong_phai_tra_luong,
            "net_operating": indirect_net_op,
            "components": {
                "doanh_thu": doanh_thu,
                "chi_phi_phat_sinh": chi_phi,
                "chi_phi_co_dinh": chi_phi_co_dinh,
                "luong_phat_sinh": luong_phat_sinh,
                "ads_phat_sinh": ads_phat_sinh,
            },
        },
        "chenh_lech": chenh_lech,
        "pct_lech": round(pct_lech, 2),
        "status": (
            "ok" if pct_lech < 5
            else "warning" if pct_lech < 20
            else "error"
        ),
        "message": (
            "✅ Cashflow trực tiếp khớp gián tiếp (chênh <5%)" if pct_lech < 5
            else f"⚠️ Lệch {pct_lech:.1f}% — kiểm tra ghi nhận sổ quỹ vs P&L"
            if pct_lech < 20
            else f"🔴 Lệch {pct_lech:.1f}% — có giao dịch chưa được hạch toán đầy đủ"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# TÌNH HÌNH TÀI CHÍNH — snapshot tổng (Tiền mặt + Nợ ai + Phải thu)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/tinh-hinh-tai-chinh")
def get_tinh_hinh_tai_chinh(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    as_of: Annotated[Optional[date], Query()] = None,
):
    """Snapshot tình hình tài chính tại 1 thời điểm — CEO nhìn vào nắm ngay:
    - Tiền mặt thực có (SUM số dư đầu + net thu/chi tới as_of) per TK
    - Tổng nợ phải trả: chi tiết NỢ AI (NCC, Ads, Lương, Vay NH)
    - Phải thu KH (KH đang nợ mình)
    - Nợ thuần = nợ phải trả - tiền mặt - phải thu
    """
    from sqlalchemy import text as _t
    today = date.today()
    as_of = as_of or today
    # Nợ ads / lương tính tới THÁNG của as_of (trước: tháng hiện tại → xem kỳ cũ vẫn ra nợ hôm nay)
    p = {"as_of": as_of, "thang_now": as_of.strftime("%Y-%m")}

    def _scalar(sql: str, params: dict | None = None) -> float:
        try:
            v = db.execute(_t(sql), params or p).scalar()
            return float(v or 0)
        except Exception:
            db.rollback()
            return 0.0

    def _rows(sql: str, params: dict | None = None) -> list[dict]:
        try:
            return [dict(r) for r in db.execute(_t(sql), params or p).mappings().all()]
        except Exception:
            db.rollback()
            return []

    def _cong_no_theo_doi_tac(loai: str) -> tuple[list[dict[str, Any]], float]:
        """Công nợ còn lại theo đối tác — cùng điều kiện với Cân đối (loai, ngay ≤ as_of,
        trang_thai ≠ 'da_tra'); tổng = Σ mọi đối tác để khớp mã 130/311."""
        # GỘP THEO TÊN CHUẨN (sửa 02/10/2026) — trước đây `GROUP BY doi_tac` THÔ.
        # `doi_tac` là chữ tự do: cùng một nhà bị ghi nhiều kiểu, nên một đối tác
        # nở ra thành nhiều dòng và người đọc tưởng dòng to nhất là tổng nợ của họ.
        # Đo trên production 02/10/2026: 59 dòng cho 21 đối tác thật.
        #   CHỊ LAN ĐỆM 12 cách viết — dòng "CHỊ LAN ĐỆM (đệm)" hiện 41.800.000
        #   trong khi nợ thật của nhà này là 38.037.000 → anh Quang đọc ra "42tr".
        #   CHIẾN PHƯƠNG 5 cách · A TOẢN MÂY 9 · CHUNG XINH 4 · A VIỆT MÂY 4.
        # Khoá gộp DÙNG ĐÚNG công thức `khoa_ncc` của view
        # ketoan.v_cong_no_phai_tra_phan_loai (bỏ mọi cụm trong ngoặc + lower với
        # COLLATE "und-x-icu") — KHÔNG viết lại luật ở đây, để hai nơi không trôi.
        # `lower()` thường KHÔNG dùng được: collation DB là C nên không hạ được chữ
        # Việt có dấu ('A TUẤN' → 'a tuẤn').
        # TỔNG không đổi (703.587.445) — chỉ đổi cách gom dòng. Phạm vi lọc
        # (trang_thai <> 'da_tra') GIỮ NGUYÊN để vẫn khớp mã 311 của Cân đối.
        # Tên hiển thị lấy bản NGẮN NHẤT trong nhóm: đó là tên trơn của nhà cung cấp
        # ("CHỊ LAN ĐỆM"), giữ nguyên chữ hoa gốc. Lấy bản dài nhất thì ra tên của
        # một phần hàng ("CHỊ LAN ĐỆM (đệm ghế pps)") — đúng số nhưng đọc như thể
        # dòng đó chỉ là một hạng mục, không phải cả nhà.
        rows = _rows("""
            WITH g AS (
                SELECT NULLIF(TRIM(regexp_replace(
                           lower(COALESCE(doi_tac, '') COLLATE "und-x-icu"),
                           '[[:space:]]*[(][^)]*[)][[:space:]]*', ' ', 'g')), '') AS khoa,
                       doi_tac, con_lai, han_thanh_toan
                  FROM ketoan.cong_no
                 WHERE loai = :loai AND ngay <= :as_of AND trang_thai <> 'da_tra'
            )
            SELECT COALESCE(
                       (SELECT g2.doi_tac FROM g g2
                         WHERE g2.khoa IS NOT DISTINCT FROM g.khoa
                         ORDER BY length(COALESCE(g2.doi_tac, '')) ASC, g2.doi_tac
                         LIMIT 1),
                       MIN(g.doi_tac)
                   ) AS doi_tac,
                   SUM(g.con_lai) AS con_lai,
                   MIN(NULLIF(g.han_thanh_toan, '')) AS han_som,
                   COUNT(*) AS so_don
              FROM g
             GROUP BY g.khoa
             ORDER BY SUM(g.con_lai) DESC
        """, {"loai": loai, "as_of": as_of})
        items, tong = [], 0.0
        for r in rows:
            con = float(r["con_lai"] or 0)
            tong += con
            if not con:
                continue
            try:
                han = date.fromisoformat(str(r["han_som"])[:10]) if r.get("han_som") else None
            except ValueError:
                han = None
            items.append({
                "doi_tac": r["doi_tac"],
                "so_tien": round(con, 0),
                "han_thanh_toan": han.isoformat() if han else None,
                "qua_han_ngay": (as_of - han).days if han and han < as_of else 0,
                "so_don": int(r["so_don"] or 0),
            })
        return items, tong

    # ── 1. TIỀN MẶT — theo từng TK, dùng so_du_dau_ky snapshot nếu có ──
    tk_rows = _rows("""
        SELECT tk.id, tk.ten_tk, tk.loai, tk.ten_nh, tk.so_du_dau
        FROM ketoan.tai_khoan_nh tk
        WHERE tk.active = TRUE
        ORDER BY tk.loai, tk.ten_tk
    """)
    tien_mat_items = []
    tong_tien = 0.0
    for r in tk_rows:
        # Số dư hết ngày as_of — cùng thuật toán neo SoDuDauKy với Sổ quỹ / mã 70 LCTT / Cân đối
        so_du = float(so_du_truoc_ngay(db, r["id"], r["ten_tk"], as_of + timedelta(days=1)))
        tien_mat_items.append({
            "ten_tk": r["ten_tk"],
            "loai": r["loai"],
            "ten_nh": r.get("ten_nh"),
            "so_du": round(so_du, 0),
        })
        tong_tien += so_du

    # ── 1b. SoQuy "lạc" — tai_khoan IS NULL hoặc không match TK nào → cộng vào
    #       1 row "Chưa phân loại" để không mất tiền vào hư vô (vd: data cũ
    #       bị bug FE [object Object], hoặc TK đã bị inactive).
    unmatched_row = _rows("""
        SELECT
          COALESCE(SUM(CASE WHEN sq.loai='thu' THEN sq.so_tien ELSE 0 END), 0) AS tong_thu,
          COALESCE(SUM(CASE WHEN sq.loai='chi' THEN sq.so_tien ELSE 0 END), 0) AS tong_chi
        FROM ketoan.so_quy sq
        WHERE sq.ngay <= :as_of
          AND (
            sq.tai_khoan IS NULL
            OR NOT EXISTS (
              SELECT 1 FROM ketoan.tai_khoan_nh tk
              WHERE tk.ten_tk = sq.tai_khoan AND tk.active = TRUE
            )
          )
    """)
    if unmatched_row:
        u = unmatched_row[0]
        u_so_du = float(u.get("tong_thu") or 0) - float(u.get("tong_chi") or 0)
        if abs(u_so_du) > 0.5:  # chỉ hiện khi đáng kể
            tien_mat_items.append({
                "ten_tk": "⚠️ TK chưa phân loại",
                "loai": "khac",
                "ten_nh": "Cần kế toán gán lại TK đúng",
                "so_du": round(u_so_du, 0),
            })
            tong_tien += u_so_du

    # ── 2. NỢ NCC — ketoan.cong_no loai='phai_tra' chưa trả, phát sinh tới as_of ──
    # QA 25/09/2026: trước lọc loai='ncc' / 'kh' — giá trị KHÔNG tồn tại trong DB (chỉ có
    # 'phai_tra' / 'phai_thu') → tab NCC + Phải thu luôn 0 trong khi Cân đối (mã 311/130)
    # có 946tr / 975tr. Nay dùng ĐÚNG điều kiện của bao_cao_can_doi._phai_tra_ncc/_phai_thu.
    no_ncc_items, no_ncc_total = _cong_no_theo_doi_tac("phai_tra")

    # ── 3. NỢ ADS — TỔNG nợ chính xác (accrual − cash) ──
    # Không breakdown per kênh vì so_quy chưa tag từng kênh — chỉ hiển thị
    # tổng phát sinh & đã trả để CEO nắm con số. Muốn breakdown per kênh
    # → cần thêm cột so_quy.kenh_ads (FB/Google/...) khi nạp tiền.
    ads_phat_sinh = _scalar("""
        SELECT COALESCE(SUM(chi_phi), 0)
        FROM marketing.ads_cost
        WHERE thang <= :thang_now
    """)
    ads_da_tra = _scalar("""
        SELECT COALESCE(SUM(so_tien), 0)
        FROM ketoan.so_quy
        WHERE loai='chi' AND phan_loai_cf='nap_ads' AND ngay <= :as_of
    """)
    no_ads_total = max(0.0, ads_phat_sinh - ads_da_tra)
    # Items: chỉ trả TỔNG (không chia per kênh — không có cách track chính xác)
    no_ads_items = [{
        "kenh": "Tổng các kênh ads (FB/Google/TikTok)",
        "phat_sinh": round(ads_phat_sinh, 0),
        "da_tra": round(ads_da_tra, 0),
        "con_no": round(no_ads_total, 0),
    }] if ads_phat_sinh > 0 else []

    # ── 4. NỢ LƯƠNG — TỔNG chính xác. Breakdown PER THÁNG (chính xác) ──
    # Không breakdown per NV vì so_quy chưa tag từng nv_id khi trả lương.
    # Muốn track chính xác per NV → khi tạo so_quy 'tra_luong' phải gắn
    # nhan_vien_id. Service có sẵn field nhan_vien_id, FE đã có dropdown
    # — chỉ cần kế toán chọn đúng NV khi nhập.
    luong_phat_sinh = _scalar("""
        SELECT COALESCE(SUM(luong_thuc_linh), 0)
        FROM hcns.payroll
        WHERE thang <= :thang_now
    """)
    luong_da_tra = _scalar("""
        SELECT COALESCE(SUM(so_tien), 0)
        FROM ketoan.so_quy
        WHERE loai='chi' AND phan_loai_cf='tra_luong' AND ngay <= :as_of
    """)
    no_luong_total = max(0.0, luong_phat_sinh - luong_da_tra)

    # Per tháng: chính xác — accrual mỗi tháng vs đã trả mỗi tháng
    luong_rows = _rows("""
        SELECT
          p.thang,
          COALESCE(SUM(p.luong_thuc_linh), 0) AS phat_sinh,
          COALESCE((
            SELECT SUM(sq.so_tien)
            FROM ketoan.so_quy sq
            WHERE sq.loai='chi' AND sq.phan_loai_cf='tra_luong'
              AND to_char(sq.ngay, 'YYYY-MM') = p.thang
              AND sq.ngay <= :as_of
          ), 0) AS da_tra
        FROM hcns.payroll p
        WHERE p.thang <= :thang_now
        GROUP BY p.thang
        ORDER BY p.thang DESC
    """)
    no_luong_items = [
        {
            "thang": r["thang"],
            "phat_sinh": round(float(r["phat_sinh"] or 0), 0),
            "da_tra": round(float(r["da_tra"] or 0), 0),
            "con_no": round(float(r["phat_sinh"] or 0) - float(r["da_tra"] or 0), 0),
        }
        for r in luong_rows
        if float(r["phat_sinh"] or 0) - float(r["da_tra"] or 0) > 0
    ]

    # ── 5. NỢ NH — từ khoan_vay đang vay ──
    vay_rows = _rows("""
        SELECT id, ma_khoan, nguon_vay, loai_vay, so_tien_vay,
               ngay_vay, ngay_dao_han, status,
               -- gốc đã trả tới as_of — cùng công thức Cân đối (_vay_ngan_han_dai_han)
               COALESCE((
                 SELECT SUM(CASE WHEN kvg.loai = 'tra_goc' THEN kvg.so_tien
                                 WHEN kvg.loai = 'tra_goc_lai' THEN COALESCE(kvg.so_tien_goc, 0)
                                 ELSE 0 END)
                 FROM ketoan.khoan_vay_giao_dich kvg
                 WHERE kvg.khoan_vay_id = kv.id AND kvg.ngay <= :as_of
               ), 0) AS da_tra_goc
        FROM ketoan.khoan_vay kv
        WHERE status = 'dang_vay' AND ngay_vay <= :as_of
        ORDER BY ngay_dao_han ASC
    """)
    no_vay_items = []
    no_vay_total = 0.0
    for r in vay_rows:
        du_no = max(0.0, float(r["so_tien_vay"] or 0) - float(r["da_tra_goc"] or 0))
        dao_han = r.get("ngay_dao_han")
        ngay_con = (dao_han - today).days if dao_han else None
        no_vay_items.append({
            "ma_khoan": r["ma_khoan"],
            "nguon_vay": r["nguon_vay"],
            "loai_vay": r["loai_vay"],
            "du_no": round(du_no, 0),
            "ngay_vay": r["ngay_vay"].isoformat() if r["ngay_vay"] else None,
            "ngay_dao_han": dao_han.isoformat() if dao_han else None,
            "ngay_con_lai": ngay_con,
        })
        no_vay_total += du_no

    # ── 6. PHẢI THU KH — ketoan.cong_no loai='phai_thu' chưa thu, phát sinh tới as_of ──
    phai_thu_items, phai_thu_total = _cong_no_theo_doi_tac("phai_thu")

    no_phai_tra_total = no_ncc_total + no_ads_total + no_luong_total + no_vay_total
    no_thuan = no_phai_tra_total - tong_tien - phai_thu_total

    return {
        "as_of": as_of.isoformat(),
        "tien_mat": {
            "tong": round(tong_tien, 0),
            "by_account": tien_mat_items,
        },
        "no_phai_tra": {
            "tong": round(no_phai_tra_total, 0),
            "by_loai": {
                "ncc": {
                    "tong": round(no_ncc_total, 0),
                    "items": no_ncc_items,
                },
                "ads": {
                    "tong": round(no_ads_total, 0),
                    "items": no_ads_items,
                },
                "luong": {
                    "tong": round(no_luong_total, 0),
                    "items": no_luong_items[:15],
                },
                "vay_nh": {
                    "tong": round(no_vay_total, 0),
                    "items": no_vay_items,
                },
            },
        },
        "phai_thu": {
            "tong": round(phai_thu_total, 0),
            "items": phai_thu_items,
        },
        "no_thuan": round(no_thuan, 0),
        "summary": {
            "tien_co": round(tong_tien, 0),
            "se_thu_ve": round(phai_thu_total, 0),
            "se_phai_tra": round(no_phai_tra_total, 0),
            "thanh_khoan_thuan": round(tong_tien + phai_thu_total - no_phai_tra_total, 0),
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# Chi tiết từng dòng — "con số này ở đâu ra"
#
# Mỗi khoá gọi CHÍNH hàm đã dựng nên số trên báo cáo, chỉ truyền thêm top_k/offset.
# Không có câu truy vấn thứ hai nào để lệch — xem docstring `_sum_items`.
# ════════════════════════════════════════════════════════════════════════════

_NHAN_CF: dict[str, str] = {
    "operating.thu_kh": "Tiền thu từ bán hàng, cung cấp dịch vụ",
    "operating.tra_ncc": "Tiền trả cho nhà cung cấp",
    "operating.tra_ads": "Tiền chi quảng cáo",
    "operating.tra_luong": "Tiền chi trả cho người lao động",
    "operating.chi_khac": "Tiền chi khác cho hoạt động kinh doanh",
    "investing.mua_ccdc": "Tiền chi mua sắm tài sản, công cụ dụng cụ",
    "investing.sua_chua": "Tiền chi sửa chữa lớn",
    "financing.vay_nh": "Tiền vay nhận được",
    "financing.tra_no_nh": "Tiền trả nợ gốc và lãi vay",
}
_NHAN_CF.update({f"{nhom}.{khoa}": khoa.replace("_", " ").capitalize()
                 for nhom, khoa, _l, _c, _f in _B03_MOI})

# Dòng TỔNG của LCTT: không có phiếu riêng, là phép cộng của các dòng trên.
# Số hạng đọc từ chính kết quả `bao_cao_cashflow()` nên cộng lại luôn bằng số trên dòng.
_CT_CF: dict[str, tuple[str, str, list]] = {
    "operating.net": ("Lưu chuyển tiền thuần từ hoạt động kinh doanh", "operating.net", [
        ("Tiền thu từ bán hàng", "operating.thu_kh", 1),
        ("Trả nhà cung cấp", "operating.tra_ncc", -1),
        ("Trả quảng cáo", "operating.tra_ads", -1),
        ("Trả người lao động", "operating.tra_luong", -1),
        ("Trả lãi vay", "operating.tra_lai_vay", -1),
        ("Nộp thuế TNDN", "operating.nop_thue_tndn", -1),
        ("Thu khác", "operating.thu_khac", 1),
        ("Chi khác", "operating.chi_khac", -1)]),
    "investing.net": ("Lưu chuyển tiền thuần từ hoạt động đầu tư", "investing.net", [
        ("Mua sắm TSCĐ, CCDC", "investing.mua_ccdc", -1),
        ("Sửa chữa lớn", "investing.sua_chua", -1),
        ("Thanh lý TSCĐ", "investing.thanh_ly_tscd", 1),
        ("Chi cho vay", "investing.chi_cho_vay", -1),
        ("Thu hồi cho vay", "investing.thu_hoi_cho_vay", 1),
        ("Chi góp vốn", "investing.chi_gop_von", -1),
        ("Thu hồi góp vốn", "investing.thu_hoi_gop_von", 1),
        ("Thu lãi, cổ tức", "investing.thu_lai", 1)]),
    "financing.net": ("Lưu chuyển tiền thuần từ hoạt động tài chính", "financing.net", [
        ("Nhận vốn góp", "financing.nhan_von", 1),
        ("Trả vốn góp", "financing.tra_von", -1),
        ("Tiền thu từ đi vay", "financing.vay_nh", 1),
        ("Trả nợ gốc, lãi vay", "financing.tra_no_nh", -1),
        ("Trả gốc thuê tài chính", "financing.tra_goc_thue_tc", -1),
        ("Chia cổ tức", "financing.chia_co_tuc", -1)]),
    "net_cashflow": ("Lưu chuyển tiền thuần trong kỳ", "net_cashflow", [
        ("Hoạt động kinh doanh", "operating.net", 1),
        ("Hoạt động đầu tư", "investing.net", 1),
        ("Hoạt động tài chính", "financing.net", 1)]),
    "so_du_dau_ky": ("Tiền và tương đương tiền đầu kỳ", "so_du_dau_ky", []),
    "so_du_cuoi_ky": ("Tiền và tương đương tiền cuối kỳ", "so_du_cuoi_ky", [
        ("Tiền đầu kỳ", "so_du_dau_ky", 1),
        ("Lưu chuyển tiền thuần trong kỳ", "net_cashflow", 1)]),
}
_NHAN_CF.update({k: v[0] for k, v in _CT_CF.items()})


def _so_cf(d: dict, path: str) -> float:
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return 0.0
        cur = cur[k]
    if isinstance(cur, dict):
        cur = cur.get("total", 0)
    try:
        return float(cur)
    except (TypeError, ValueError):
        return 0.0


_B03_THEO_KHOA = {f"{nhom}.{khoa}": (loai, cf, loc)
                  for nhom, khoa, loai, cf, loc in _B03_MOI}


def _chi_tiet_cf(db: Session, khoa: str, tu: date, den: date,
                 top_k: int, offset: int) -> Optional[dict[str, Any]]:
    """Gọi đúng hàm đã tính dòng đó. `None` nếu khoá không có."""
    if khoa in _B03_THEO_KHOA:
        loai, cf, loc = _B03_THEO_KHOA[khoa]
        return _b03_moi(db, tu, den, loai, cf, loc, top_k=top_k, offset=offset)
    if khoa == "operating.chi_khac":
        return _operating_chi_khac(db, tu, den, _full_chi_classified_ids(db, tu, den),
                                   top_k=top_k, offset=offset)
    ham = {
        "operating.thu_kh": _operating_thu_kh,
        "operating.tra_ncc": _operating_tra_ncc,
        "operating.tra_ads": _operating_tra_ads,
        "operating.tra_luong": _operating_tra_luong,
        "investing.mua_ccdc": _investing_mua_ccdc,
        "investing.sua_chua": _investing_sua_chua,
        "financing.vay_nh": _financing_vay,
        "financing.tra_no_nh": _financing_tra_no,
    }.get(khoa)
    if ham is None:
        return None
    return ham(db, tu, den, top_k=top_k, offset=offset)


_COT_SO_QUY = [
    {"key": "ngay", "nhan": "Ngày", "kieu": "ngay"},
    {"key": "tai_khoan", "nhan": "Tài khoản"},
    {"key": "noi_dung", "nhan": "Nội dung"},
    {"key": "lien_quan", "nhan": "Liên quan"},
    {"key": "ghi_chu", "nhan": "Ghi chú"},
    {"key": "so_tien", "nhan": "Số tiền", "kieu": "tien"},
]


@router.get("/cashflow/chi-tiet")
def bao_cao_cashflow_chi_tiet(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, Depends(require_ketoan_user)],
    khoa: str = Query(..., description="Khoá dòng, vd 'operating.thu_kh'"),
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = Query(None),
    trang: int = Query(1, ge=1),
    so_dong: int = Query(50, ge=1, le=200),
):
    """Các phiếu thu/chi làm nên một dòng Lưu chuyển tiền tệ, có phân trang."""
    tu, den = _resolve_range(from_, to)
    if khoa == "so_du_dau_ky":
        # Số dư từng tài khoản tiền ngay trước ngày `tu` — dùng CHÍNH hàm mà báo cáo
        # gọi (`so_du_truoc_ngay`), nên cộng lại luôn bằng dòng mã 60.
        tks = db.execute(
            select(TaiKhoanNH.id, TaiKhoanNH.ten_tk).where(TaiKhoanNH.active.is_(True))
        ).all()
        dong = [{"tai_khoan": tk.ten_tk,
                 "so_tien": _f(so_du_truoc_ngay(db, tk.id, tk.ten_tk, tu))} for tk in tks]
        return {
            "ok": True, "khoa": khoa, "nhan": "Tiền và tương đương tiền đầu kỳ",
            "nguon": "ketoan.tai_khoan_nh + mốc số dư đầu kỳ",
            "giai_thich": "Số dư từng tài khoản tiền ngay trước ngày bắt đầu kỳ.",
            "ghi_chu": _canh_bao_dau_ky(db, tu) or "",
            "tu": tu.isoformat(), "den": den.isoformat(),
            "tong": round(sum(x["so_tien"] for x in dong), 2),
            "so_dong": len(dong), "trang": 1, "so_trang": 1, "so_dong_moi_trang": so_dong,
            "cot": [{"key": "tai_khoan", "nhan": "Tài khoản"},
                    {"key": "so_tien", "nhan": "Số dư", "kieu": "tien"}],
            "dong": dong, "dieu_chinh": [],
        }
    if khoa in _CT_CF:
        nhan, duong_dan, so_hang = _CT_CF[khoa]
        bc = bao_cao_cashflow(db, user, from_=tu, to=den)
        return {
            "ok": True, "khoa": khoa, "nhan": nhan,
            "nguon": "Tính từ các dòng khác của báo cáo",
            "giai_thich": "Dòng này không có phiếu riêng — nó là phép cộng của các dòng trên.",
            "tu": tu.isoformat(), "den": den.isoformat(),
            "tong": round(_so_cf(bc, duong_dan), 2),
            "so_dong": len(so_hang), "trang": 1, "so_trang": 1, "so_dong_moi_trang": so_dong,
            "cot": [{"key": "khoan", "nhan": "Số hạng"},
                    {"key": "so_tien", "nhan": "Số tiền", "kieu": "tien"}],
            "dong": [{"khoan": ("− " if d < 0 else "+ ") + n,
                      "so_tien": round(_so_cf(bc, pth) * d, 2)} for n, pth, d in so_hang],
            "dieu_chinh": [],
        }
    kq = _chi_tiet_cf(db, khoa, tu, den, top_k=so_dong, offset=(trang - 1) * so_dong)
    if kq is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, {
            "loi": "khoa_chua_khai",
            "thong_bao": f"Không có dòng '{khoa}' trong Lưu chuyển tiền tệ.",
            "khoa_dang_co": sorted(_NHAN_CF.keys()),
        })
    n = int(kq.get("so_dong", len(kq.get("items", []))))
    so_trang = max(1, -(-n // so_dong))
    if trang > so_trang:
        kq = _chi_tiet_cf(db, khoa, tu, den, top_k=so_dong, offset=(so_trang - 1) * so_dong)
    return {
        "ok": True, "khoa": khoa, "nhan": _NHAN_CF.get(khoa, khoa),
        "nguon": "ketoan.so_quy" if not khoa.startswith("financing.") else
                 "ketoan.khoan_vay_giao_dich + ketoan.so_quy",
        "giai_thich": "Các phiếu thu/chi đã được cộng vào dòng này trong kỳ.",
        "tu": tu.isoformat(), "den": den.isoformat(),
        "tong": kq["total"], "so_dong": n,
        "trang": min(trang, so_trang), "so_trang": so_trang, "so_dong_moi_trang": so_dong,
        "cot": _COT_SO_QUY, "dong": kq.get("items", []), "dieu_chinh": [],
    }
