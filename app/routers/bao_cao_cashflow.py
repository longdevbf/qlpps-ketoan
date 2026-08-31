"""Báo Cáo Lưu Chuyển Tiền Tệ (Cashflow Statement) — trong khoảng kỳ.

Endpoint: GET /api/bao-cao/cashflow?from=YYYY-MM-DD&to=YYYY-MM-DD

Trả 3 nhóm dòng tiền (dựa trên `ketoan.so_quy`):
  I.  HĐ Kinh Doanh: Thu KH - Trả NCC - Trả Ads - Trả Lương - Chi khác (operating)
  II. HĐ Đầu Tư: Mua CCDC - Sửa chữa lớn (investing)
  III.HĐ Tài Chính: Vay NH (thu) - Trả nợ NH/Lãi vay (chi) (financing)

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

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, func, or_, select, text
from sqlalchemy.orm import Session

from shared.auth import JWTPayload
from shared.db import get_db

from ..models import ChiPhiPhatSinh, SoQuy, TaiKhoanNH, SoDuDauKy
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


# ════════════════════════════════════════════════════════════════════════════
# Group queries (sum + items top 5)
# ════════════════════════════════════════════════════════════════════════════

def _sum_items(
    db: Session,
    base_filters: list,
    *,
    top_k: int = 5,
) -> dict[str, Any]:
    """Trả {total, items: top-K transactions by so_tien desc}."""
    total = db.scalar(
        select(func.coalesce(func.sum(SoQuy.so_tien), 0)).where(and_(*base_filters))
    ) or Decimal("0")

    rows = db.execute(
        select(SoQuy)
        .where(and_(*base_filters))
        .order_by(SoQuy.so_tien.desc(), SoQuy.ngay.desc())
        .limit(top_k)
    ).scalars().all()

    return {"total": _f(total), "items": [_row(r) for r in rows]}


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


def _operating_thu_kh(db: Session, tu: date, den: date) -> dict[str, Any]:
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
    ])


def _operating_tra_ncc(db: Session, tu: date, den: date) -> dict[str, Any]:
    return _sum_items(db, [
        SoQuy.loai == "chi",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
        _by_cf_or_heuristic("tra_ncc", _ilike_any(SoQuy.lien_quan, _LIEN_QUAN_NCC)),
    ])


def _operating_tra_ads(db: Session, tu: date, den: date) -> dict[str, Any]:
    return _sum_items(db, [
        SoQuy.loai == "chi",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
        _by_cf_or_heuristic("nap_ads", or_(
            _ilike_any(SoQuy.lien_quan, _LIEN_QUAN_ADS),
            _ilike_any(SoQuy.ghi_chu, ("ads", "marketing", "facebook", "google")),
            _ilike_any(SoQuy.noi_dung, ("ads", "marketing", "facebook", "google")),
        )),
    ])


def _operating_tra_luong(db: Session, tu: date, den: date) -> dict[str, Any]:
    return _sum_items(db, [
        SoQuy.loai == "chi",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
        _by_cf_or_heuristic("tra_luong", or_(
            _ilike_any(SoQuy.lien_quan, _LIEN_QUAN_LUONG),
            _ilike_any(SoQuy.ghi_chu, ("lương", "luong", "salary", "payroll")),
            _ilike_any(SoQuy.noi_dung, ("lương", "luong", "salary", "payroll")),
        )),
    ])


def _investing_mua_ccdc(db: Session, tu: date, den: date) -> dict[str, Any]:
    return _sum_items(db, [
        SoQuy.loai == "chi",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
        _by_cf_or_heuristic("mua_ccdc", or_(
            _ilike_any(SoQuy.lien_quan, _LIEN_QUAN_CCDC),
            _ilike_any(SoQuy.ghi_chu, ("ccdc", "tài sản", "tai san", "tscd")),
        )),
    ])


def _investing_sua_chua(db: Session, tu: date, den: date) -> dict[str, Any]:
    return _sum_items(db, [
        SoQuy.loai == "chi",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
        _by_cf_or_heuristic("sua_chua_lon", or_(
            _ilike_any(SoQuy.lien_quan, _LIEN_QUAN_SUACHUA),
            _ilike_any(SoQuy.ghi_chu, ("sửa chữa", "sua chua", "bảo trì", "bao tri")),
        )),
    ])


def _financing_from_kvgd(
    db: Session, tu: date, den: date, loai_list: tuple[str, ...],
) -> dict[str, Any]:
    """Đọc giao dịch khoản vay từ `ketoan.khoan_vay_giao_dich` — SOURCE OF TRUTH
    cho hoạt động tài chính (giải ngân / trả gốc / trả lãi / đáo hạn).
    """
    from sqlalchemy import text as _t
    placeholders = ",".join(f"'{l}'" for l in loai_list)
    sql = f"""
        SELECT g.id, g.ngay, g.loai, g.so_tien, kv.ma_khoan, kv.nguon_vay,
               g.ghi_chu
        FROM ketoan.khoan_vay_giao_dich g
        JOIN ketoan.khoan_vay kv ON kv.id = g.khoan_vay_id
        WHERE g.loai IN ({placeholders})
          AND g.ngay BETWEEN :tu AND :den
        ORDER BY g.so_tien DESC, g.ngay DESC
    """
    try:
        rows = db.execute(_t(sql), {"tu": tu, "den": den}).mappings().all()
    except Exception:
        db.rollback()
        return {"total": 0.0, "items": []}
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
        for r in rows[:5]
    ]
    return {"total": total, "items": items}


def _financing_vay(db: Session, tu: date, den: date) -> dict[str, Any]:
    """Vay nhận về (Thu) = giải ngân từ khoan_vay_giao_dich + so_quy manual.

    Tránh double count với so_quy đã auto-link (lien_quan='vay_<kvgd.id>').
    """
    kvgd = _financing_from_kvgd(db, tu, den, ("giai_ngan",))
    sq = _sum_items(db, [
        SoQuy.loai == "thu",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
        SoQuy.phan_loai_cf == "vay_nh",
        ~SoQuy.lien_quan.ilike("vay\\_%", escape="\\"),
    ])
    return {
        "total": kvgd["total"] + sq["total"],
        "items": (kvgd["items"] + sq["items"])[:5],
    }


def _financing_tra_no(db: Session, tu: date, den: date) -> dict[str, Any]:
    """Trả gốc + lãi (Chi) = trả nợ từ khoan_vay_giao_dich + so_quy manual."""
    kvgd = _financing_from_kvgd(db, tu, den, ("tra_goc", "tra_lai", "tra_goc_lai", "dao_han"))
    sq = _sum_items(db, [
        SoQuy.loai == "chi",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
        SoQuy.phan_loai_cf == "tra_nh",
        ~SoQuy.lien_quan.ilike("vay\\_%", escape="\\"),
    ])
    return {
        "total": kvgd["total"] + sq["total"],
        "items": (kvgd["items"] + sq["items"])[:5],
    }


def _operating_chi_khac(
    db: Session,
    tu: date,
    den: date,
    excl_ids: set[int],
) -> dict[str, Any]:
    """Chi khác = chi trong kỳ KHÔNG thuộc các nhóm đã phân loại (NCC/Ads/Lương/Đầu tư/Tài chính)."""
    base_filters = [
        SoQuy.loai == "chi",
        SoQuy.ngay >= tu, SoQuy.ngay <= den,
    ]
    if excl_ids:
        base_filters.append(~SoQuy.id.in_(excl_ids))

    total = db.scalar(
        select(func.coalesce(func.sum(SoQuy.so_tien), 0)).where(and_(*base_filters))
    ) or Decimal("0")
    rows = db.execute(
        select(SoQuy)
        .where(and_(*base_filters))
        .order_by(SoQuy.so_tien.desc(), SoQuy.ngay.desc())
        .limit(5)
    ).scalars().all()
    return {"total": _f(total), "items": [_row(r) for r in rows]}


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
    """Per TaiKhoanNH: thu/chi trong kỳ + so_du_cuoi (= so_du_dau + Σ(thu-chi) up to `den`)."""
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
        # Số dư cuối tài khoản = so_du_dau + tổng (thu - chi) up to den
        thu_total = db.scalar(
            select(func.coalesce(func.sum(SoQuy.so_tien), 0)).where(
                SoQuy.tai_khoan == tk.ten_tk,
                SoQuy.loai == "thu",
                SoQuy.ngay <= den,
            )
        ) or Decimal("0")
        chi_total = db.scalar(
            select(func.coalesce(func.sum(SoQuy.so_tien), 0)).where(
                SoQuy.tai_khoan == tk.ten_tk,
                SoQuy.loai == "chi",
                SoQuy.ngay <= den,
            )
        ) or Decimal("0")
        so_du_cuoi = _f(tk.so_du_dau) + _f(thu_total) - _f(chi_total)

        thu_f, chi_f = _f(thu_in), _f(chi_in)
        out.append({
            "ten_tk": tk.ten_tk,
            "loai": tk.loai,
            "thu": thu_f,
            "chi": chi_f,
            "net": thu_f - chi_f,
            "so_du_cuoi": so_du_cuoi,
        })
    return out


def _so_du_dau_ky(db: Session, tu: date) -> float:
    """Tổng số dư đầu kỳ tại thời điểm `tu`.

    Per-account: lấy SoDuDauKy snapshot mới nhất (thang ≤ tu) làm base, cộng
    giao dịch từ tháng snapshot đến `tu`. Không có snapshot → fallback
    TaiKhoanNH.so_du_dau + tất cả giao dịch trước `tu`.
    """
    tks = db.execute(
        select(TaiKhoanNH.id, TaiKhoanNH.ten_tk, TaiKhoanNH.so_du_dau)
        .where(TaiKhoanNH.active.is_(True))
    ).all()
    total = Decimal("0")
    for tk in tks:
        snap = db.execute(
            select(SoDuDauKy.thang, SoDuDauKy.so_du)
            .where(SoDuDauKy.tai_khoan_id == tk.id, SoDuDauKy.thang <= tu)
            .order_by(SoDuDauKy.thang.desc())
            .limit(1)
        ).first()
        if snap:
            base = Decimal(snap.so_du or 0)
            since = snap.thang
        else:
            base = Decimal(tk.so_du_dau or 0)
            since = None
        thu_q = select(func.coalesce(func.sum(SoQuy.so_tien), 0)).where(
            SoQuy.tai_khoan == tk.ten_tk,
            SoQuy.loai == "thu",
            SoQuy.ngay < tu,
        )
        chi_q = select(func.coalesce(func.sum(SoQuy.so_tien), 0)).where(
            SoQuy.tai_khoan == tk.ten_tk,
            SoQuy.loai == "chi",
            SoQuy.ngay < tu,
        )
        if since:
            thu_q = thu_q.where(SoQuy.ngay >= since)
            chi_q = chi_q.where(SoQuy.ngay >= since)
        thu = db.scalar(thu_q) or Decimal("0")
        chi = db.scalar(chi_q) or Decimal("0")
        total += base + Decimal(thu) - Decimal(chi)
    return _f(total)


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
    )
    net_investing = -(mua_ccdc["total"] + sua_chua["total"])
    net_financing = vay_nh["total"] - tra_no_nh["total"]
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
        "operating": {
            "thu_kh": thu_kh,
            "tra_ncc": tra_ncc,
            "tra_ads": tra_ads,
            "tra_luong": tra_luong,
            "chi_khac": chi_khac,
            "net": net_operating,
        },
        "investing": {
            "mua_ccdc": mua_ccdc,
            "sua_chua": sua_chua,
            "net": net_investing,
        },
        "financing": {
            "vay_nh": vay_nh,
            "tra_no_nh": tra_no_nh,
            "net": net_financing,
        },
        "net_cashflow": net_cashflow,
        "so_du_cuoi_ky": so_du_cuoi,
        "daily": daily,
        "by_account": by_acc,
    }


def _full_chi_classified_ids(db: Session, tu: date, den: date) -> set[int]:
    """Lấy đầy đủ ID các so_quy chi đã thuộc nhóm phân loại (NCC/Ads/Lương/CCDC/SửaChữa/TrảNợ).

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
    ads_da_tra = _scalar(
        "SELECT COALESCE(SUM(so_tien),0) FROM ketoan.so_quy "
        "WHERE loai='chi' AND ngay BETWEEN :tu AND :den AND phan_loai_cf='nap_ads'"
    )

    # 2. Lương — accrual từ hcns.payroll
    luong_phat_sinh = _scalar(
        "SELECT COALESCE(SUM(luong_thuc_linh),0) FROM hcns.payroll "
        "WHERE thang BETWEEN :thang_tu AND :thang_den"
    )
    luong_da_tra = _scalar(
        "SELECT COALESCE(SUM(so_tien),0) FROM ketoan.so_quy "
        "WHERE loai='chi' AND ngay BETWEEN :tu AND :den AND phan_loai_cf='tra_luong'"
    )

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
    ncc_da_tra = _scalar(
        "SELECT COALESCE(SUM(so_tien),0) FROM ketoan.so_quy "
        "WHERE loai='chi' AND ngay BETWEEN :tu AND :den AND phan_loai_cf='tra_ncc'"
    )

    # 4. Vay — vay/trả nợ
    vay_nhan = _scalar(
        "SELECT COALESCE(SUM(so_tien),0) FROM ketoan.so_quy "
        "WHERE loai='thu' AND ngay BETWEEN :tu AND :den AND phan_loai_cf='vay_nh'"
    )
    vay_tra = _scalar(
        "SELECT COALESCE(SUM(so_tien),0) FROM ketoan.so_quy "
        "WHERE loai='chi' AND ngay BETWEEN :tu AND :den AND phan_loai_cf='tra_nh'"
    )

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
    p = {"as_of": as_of, "thang_now": today.strftime("%Y-%m")}

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
        tk_id = r["id"]
        # Lấy snapshot gần nhất <= as_of
        snap = db.execute(
            text("""
                SELECT thang, so_du FROM ketoan.so_du_dau_ky
                WHERE tai_khoan_id = :tid AND thang <= :asof
                ORDER BY thang DESC LIMIT 1
            """),
            {"tid": tk_id, "asof": as_of},
        ).first()
        if snap:
            base = float(snap[1] or 0)
            since = snap[0]
        else:
            base = float(r.get("so_du_dau") or 0)
            since = None

        where_since = "AND ngay >= :since" if since else ""
        params_tk = {"tk": r["ten_tk"], "asof": as_of}
        if since:
            params_tk["since"] = since

        thu = db.execute(
            text(f"SELECT COALESCE(SUM(so_tien),0) FROM ketoan.so_quy WHERE tai_khoan=:tk AND loai='thu' AND ngay<=:asof {where_since}"),
            params_tk,
        ).scalar() or 0
        chi = db.execute(
            text(f"SELECT COALESCE(SUM(so_tien),0) FROM ketoan.so_quy WHERE tai_khoan=:tk AND loai='chi' AND ngay<=:asof {where_since}"),
            params_tk,
        ).scalar() or 0

        so_du = base + float(thu) - float(chi)
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

    # ── 2. NỢ NCC — từ ketoan.cong_no chưa trả ──
    ncc_rows = _rows("""
        SELECT doi_tac, SUM(con_lai) AS con_lai, MIN(han_thanh_toan) AS han_som,
               COUNT(*) AS so_don
        FROM ketoan.cong_no
        WHERE loai='ncc' AND con_lai > 0
        GROUP BY doi_tac
        ORDER BY con_lai DESC
        LIMIT 50
    """)
    no_ncc_items = []
    no_ncc_total = 0.0
    for r in ncc_rows:
        con = float(r["con_lai"] or 0)
        han = r.get("han_som")
        qua_han = (today - han).days if han and han < today else 0
        no_ncc_items.append({
            "doi_tac": r["doi_tac"],
            "so_tien": round(con, 0),
            "han_thanh_toan": han.isoformat() if han else None,
            "qua_han_ngay": qua_han,
            "so_don": int(r["so_don"] or 0),
        })
        no_ncc_total += con

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
               -- tổng đã trả gốc cho khoản vay này
               COALESCE((
                 SELECT SUM(so_tien) FROM ketoan.khoan_vay_giao_dich kvg
                 WHERE kvg.khoan_vay_id = kv.id AND kvg.loai IN ('tra_goc','tra_goc_lai')
               ), 0) AS da_tra_goc
        FROM ketoan.khoan_vay kv
        WHERE status = 'dang_vay'
        ORDER BY ngay_dao_han ASC
    """)
    no_vay_items = []
    no_vay_total = 0.0
    for r in vay_rows:
        du_no = float(r["so_tien_vay"] or 0) - float(r["da_tra_goc"] or 0)
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

    # ── 6. PHẢI THU KH — từ ketoan.cong_no loại='kh' chưa thu ──
    pt_rows = _rows("""
        SELECT doi_tac, SUM(con_lai) AS con_lai, MIN(han_thanh_toan) AS han_som,
               COUNT(*) AS so_don
        FROM ketoan.cong_no
        WHERE loai='kh' AND con_lai > 0
        GROUP BY doi_tac
        ORDER BY con_lai DESC
        LIMIT 50
    """)
    phai_thu_items = []
    phai_thu_total = 0.0
    for r in pt_rows:
        con = float(r["con_lai"] or 0)
        han = r.get("han_som")
        qua_han = (today - han).days if han and han < today else 0
        phai_thu_items.append({
            "doi_tac": r["doi_tac"],
            "so_tien": round(con, 0),
            "han_thanh_toan": han.isoformat() if han else None,
            "qua_han_ngay": qua_han,
            "so_don": int(r["so_don"] or 0),
        })
        phai_thu_total += con

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
