"""Báo Cáo aggregates — P&L tổng hợp + grouped doanh thu / chi phí / công nợ.

Cross-app reads (luong/donhang/ads) gộp vào `/tong-hop` cho P&L đầy đủ.

Perf: dashboard `/api/bao-cao?thang=X` được TTL cache 30s in-process. CRUD
DoanhThu/ChiPhi/CongNo invalidate cache qua `_invalidate_dashboard_cache(thang)`.

Sprint Week 12:
  - Thêm field breakdown cho /tong-hop (lương/chi-phí/ads theo phòng-ban/quỹ/kênh).
  - Endpoint mới: /per-nv (doanh số per NV từ baogia.quotes raw SQL).
  - Endpoint mới: /snapshot/{thang} GET + POST (lưu snapshot JSONB).
"""
import json
import time
from datetime import date as date_cls, datetime
from decimal import Decimal
from hashlib import md5
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import BaoCaoSnapshot, ChiPhiPhatSinh, CongNo, DoanhThu
from ..schemas import (
    BaoCaoTongHopOut, BaoCaoCongNoOut, GroupedAmount,
)
from ..services import (
    sum_doanh_thu, sum_chi_phi_phat_sinh, sum_chi_phi_co_dinh,
    sum_cong_no_by_loai, group_by_date_doanh_thu, group_by_loai_chi_phi,
    read_luong_total, read_don_hang_total, read_ads_total,
)
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


# In-process TTL cache cho dashboard endpoint /api/bao-cao
_DASHBOARD_CACHE: dict[str, tuple[float, dict]] = {}
_DASHBOARD_TTL = 30.0  # seconds


def invalidate_dashboard_cache(thang: Optional[str] = None) -> None:
    """Clear cache khi có CRUD lớn (DoanhThu/ChiPhi/CongNo create/update/delete)."""
    if thang is None:
        _DASHBOARD_CACHE.clear()
    else:
        _DASHBOARD_CACHE.pop(thang, None)


def _resolve_range(
    tu: Optional[date_cls], den: Optional[date_cls]
) -> tuple[date_cls, date_cls]:
    """Default: tháng hiện tại (1 → today)."""
    today = date_cls.today()
    if not den:
        den = today
    if not tu:
        tu = today.replace(day=1)
    return tu, den


# ---------------- raw SQL fail-soft helpers ----------------

def _safe_dict_sum(db: Session, sql: str, **params) -> dict[str, float]:
    """Run SQL `SELECT key, SUM(amount)` → dict[key,float]. Fail-soft trả {}."""
    try:
        rows = db.execute(text(sql), params).all()
    except (ProgrammingError, OperationalError):
        db.rollback()
        return {}
    out: dict[str, float] = {}
    for k, v in rows:
        key = str(k) if k is not None else "Khác"
        out[key] = float(v or 0)
    return out


def _luong_by_phong_ban(db: Session, thang: str) -> dict[str, float]:
    """SUM(payroll.thuc_linh) GROUP BY employees.phong_ban (raw SQL fail-soft)."""
    if not thang:
        return {}
    sql = """
        SELECT COALESCE(e.phong_ban, 'Khác') AS phong_ban,
               COALESCE(SUM(p.thuc_linh), 0)
        FROM hcns.payroll p
        LEFT JOIN hcns.employees e ON e.id = p.employee_id
        WHERE p.thang = :thang
        GROUP BY e.phong_ban
        ORDER BY 2 DESC
    """
    return _safe_dict_sum(db, sql, thang=thang)


def _ads_by_kenh(db: Session, tu: date_cls, den: date_cls) -> dict[str, float]:
    """SUM(ads_cost.chi_phi) GROUP BY kenh (raw SQL fail-soft)."""
    sql = """
        SELECT COALESCE(kenh, 'Khác') AS kenh,
               COALESCE(SUM(chi_phi), 0)
        FROM marketing.ads_cost
        WHERE ngay >= :tu AND ngay <= :den
        GROUP BY kenh
        ORDER BY 2 DESC
    """
    return _safe_dict_sum(db, sql, tu=tu, den=den)


def _doanh_so_per_nv(db: Session, tu: date_cls, den: date_cls) -> dict[str, float]:
    """SUM(quotes.tong_don) GROUP BY nv_kd (raw SQL fail-soft)."""
    sql = """
        SELECT COALESCE(nv_kd, 'Khác') AS nv,
               COALESCE(SUM(tong_don), 0)
        FROM baogia.quotes
        WHERE created_at::date >= :tu AND created_at::date <= :den
        GROUP BY nv_kd
        ORDER BY 2 DESC
    """
    return _safe_dict_sum(db, sql, tu=tu, den=den)


# ---------------- /tong-hop ----------------

# ─────────────────────────────────────────────────────────────────────────────
# FE Dashboard endpoint — `GET /api/bao-cao?thang=YYYY-MM`
# Trả shape FE template `index.html::loadBaoCao` đang đọc.
# ─────────────────────────────────────────────────────────────────────────────

@router.get("")
def bao_cao_dashboard(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    request: Request,
    response: Response,
    thang: Optional[str] = Query(None),
) -> Any:
    """Dashboard tổng hợp tháng. Map ra shape FE đọc.

    Format `thang`: 'YYYY-MM'. Nếu không truyền → tháng hiện tại.
    """
    from calendar import monthrange
    if not thang:
        thang = datetime.now().strftime("%Y-%m")
    try:
        yr, mo = map(int, thang.split("-"))
    except (ValueError, IndexError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "thang format YYYY-MM")

    # Redis cache 30s (dashboard) — fallback in-process nếu Redis lỗi.
    try:
        from ..main import cache_get_or_set as _cache_gos  # type: ignore
    except Exception:
        _cache_gos = None  # type: ignore

    # TTL cache (30s) — giữ in-process làm L1 (rất nhanh, không network).
    now = time.time()
    cached = _DASHBOARD_CACHE.get(thang)
    if cached and (now - cached[0]) < _DASHBOARD_TTL:
        out = cached[1]
        # ETag + 304 fail-soft
        try:
            body = json.dumps(out, sort_keys=True, default=str, ensure_ascii=False)
            etag = 'W/"' + md5(body.encode()).hexdigest() + '"'
            if request.headers.get("if-none-match") == etag:
                return Response(status_code=304, headers={"ETag": etag})
            response.headers["ETag"] = etag
            response.headers["Cache-Control"] = "private, max-age=10, must-revalidate"
            response.headers["Vary"] = "Cookie"
        except Exception:
            pass
        return out

    tu = date_cls(yr, mo, 1)
    den = date_cls(yr, mo, monthrange(yr, mo)[1])

    th = _build_tong_hop(db, tu, den)

    # Cross-app stats: NV count, đơn hàng count, marketing data/inbox
    tong_nv = 0
    so_don = 0
    vat_dau_ra = 0.0
    so_data_mkt = 0
    so_inbox_mkt = 0
    nhansu_by_pb: list[tuple[str, int]] = []
    try:
        from hcns.app.models import Employee  # noqa: WPS433
        rows = db.execute(
            select(
                func.coalesce(Employee.phong_ban, "Khác"),
                func.count(Employee.ma_nv),
            )
            .where(Employee.trang_thai == "Đang làm")
            .group_by(Employee.phong_ban)
            .order_by(func.count(Employee.ma_nv).desc())
        ).all()
        nhansu_by_pb = [(str(p), int(c)) for p, c in rows]
        tong_nv = sum(c for _, c in nhansu_by_pb)
    except Exception:
        pass

    try:
        from baogia.app.models import Quote  # noqa: WPS433
        # Số đơn + VAT ĐẦU RA (tien_thue) — theo THÁNG DUYỆT (khớp trang Đơn Hàng).
        _row = db.execute(
            select(
                func.count(Quote.id),
                func.coalesce(func.sum(Quote.tien_thue), 0),
            )
            .where(Quote.duyet_status == "approved")
            .where(Quote.duyet_luc.isnot(None))
            .where(func.date(Quote.duyet_luc) >= tu)
            .where(func.date(Quote.duyet_luc) <= den)
        ).one()
        so_don = int(_row[0] or 0)
        vat_dau_ra = float(_row[1] or 0)
    except Exception:
        pass

    try:
        from marketing.app.models import AdsCost  # noqa: WPS433
        row = db.execute(
            select(
                func.coalesce(func.sum(AdsCost.so_data), 0),
                func.coalesce(func.sum(AdsCost.so_inbox), 0),
            ).where(AdsCost.thang == thang)
        ).one()
        so_data_mkt = int(row[0] or 0)
        so_inbox_mkt = int(row[1] or 0)
    except Exception:
        pass

    # Tổng công nợ (phải thu + phải trả)
    tong_cong_no = 0.0
    try:
        rows = db.execute(
            select(CongNo.loai, func.coalesce(func.sum(CongNo.so_tien), 0))
            .where(CongNo.ngay >= tu, CongNo.ngay <= den)
            .group_by(CongNo.loai)
        ).all()
        tong_cong_no = float(sum(v or 0 for _, v in rows))
    except Exception:
        pass

    # ChiPhi by loại — cho bar chart
    cp_loai_rows = db.execute(
        select(
            func.coalesce(ChiPhiPhatSinh.loai_chi_phi, "Khác"),
            func.coalesce(func.sum(ChiPhiPhatSinh.so_tien), 0),
        )
        .where(ChiPhiPhatSinh.ngay >= tu, ChiPhiPhatSinh.ngay <= den)
        .group_by(ChiPhiPhatSinh.loai_chi_phi)
        .order_by(func.sum(ChiPhiPhatSinh.so_tien).desc())
    ).all()
    cp_by_loai = [(str(k), float(v or 0)) for k, v in cp_loai_rows]

    # DoanhThu by loại
    dt_loai_rows = db.execute(
        select(
            func.coalesce(DoanhThu.loai, DoanhThu.loai_thanh_toan, "Khác"),
            func.coalesce(func.sum(DoanhThu.so_tien), 0),
        )
        .where(DoanhThu.ngay >= tu, DoanhThu.ngay <= den)
        .group_by(DoanhThu.loai, DoanhThu.loai_thanh_toan)
        .order_by(func.sum(DoanhThu.so_tien).desc())
    ).all()
    dt_by_loai = [(str(k), float(v or 0)) for k, v in dt_loai_rows]

    # DoanhThu per NV (cross-app baogia)
    dt_by_nv: list[tuple[str, float]] = []
    try:
        from baogia.app.models import Quote  # noqa: WPS433
        rows = db.execute(
            select(
                func.coalesce(Quote.salesperson, "Khác"),
                func.coalesce(func.sum(Quote.tong_chua_thue), 0),
            )
            .where(Quote.duyet_status == "approved")
            .where(Quote.duyet_luc.isnot(None))
            .where(func.date(Quote.duyet_luc) >= tu)
            .where(func.date(Quote.duyet_luc) <= den)
            .group_by(Quote.salesperson)
            .order_by(func.sum(Quote.tong_chua_thue).desc())
            .limit(15)
        ).all()
        dt_by_nv = [(str(k), float(v or 0)) for k, v in rows]
    except Exception:
        pass

    # ADS by kênh + Lương by phòng ban (đã có trong _build_tong_hop)
    ads_by_kenh = sorted(th.ads_by_kenh.items(), key=lambda x: -x[1])
    luong_by_pb = sorted(th.luong_by_phong_ban.items(), key=lambda x: -x[1])

    result: dict = {
        "thang": thang,
        "tu_ngay": tu.isoformat(),
        "den_ngay": den.isoformat(),
        # P&L
        "tong_doanh_thu": float(th.tong_doanh_thu) + float(th.tong_don_hang_muahang),
        "tong_kt_thu": float(th.tong_doanh_thu),
        "tong_don_hang": float(th.tong_don_hang_muahang),
        "tong_chi_phi": float(th.tong_chi_phi),
        "tong_bien_phi": float(th.tong_chi_phi_phat_sinh),
        "tong_dinh_phi": float(th.tong_chi_phi_co_dinh),
        "tong_luong": float(th.tong_luong_hcns),
        "tong_ads": float(th.tong_ads_marketing),
        "loi_nhuan_gop": float(th.loi_nhuan_gop),
        "loi_nhuan_truoc_thue": float(th.loi_nhuan_truoc_thue),
        # KPIs
        "tong_nv": tong_nv,
        "so_don": int(so_don),
        "vat_dau_ra": float(vat_dau_ra),
        "so_data_mkt": so_data_mkt,
        "so_inbox_mkt": so_inbox_mkt,
        "tong_cong_no": tong_cong_no,
        # Charts (FE expects [[label, val], ...])
        "cp_by_loai": cp_by_loai,
        "dt_by_loai": dt_by_loai,
        "dt_by_nv": dt_by_nv,
        "ads_by_kenh": ads_by_kenh,
        "luong_by_pb": luong_by_pb,
        "nhansu_by_pb": nhansu_by_pb,
    }
    _DASHBOARD_CACHE[thang] = (now, result)

    # Redis L2 cache (30s) — share giữa workers.
    if _cache_gos is not None:
        try:
            r_key = f"ketoan:dash:bao_cao:{thang}"
            # Set vào Redis (compute_fn trả về result luôn).
            _cache_gos(r_key, 30, lambda: result)
        except Exception:
            pass

    # ETag + 304 fail-soft cho list endpoint chính.
    try:
        body = json.dumps(result, sort_keys=True, default=str, ensure_ascii=False)
        etag = 'W/"' + md5(body.encode()).hexdigest() + '"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag})
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = "private, max-age=10, must-revalidate"
        response.headers["Vary"] = "Cookie"
    except Exception:
        pass
    return result


@router.get("/tong-hop", response_model=BaoCaoTongHopOut)
def bao_cao_tong_hop(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu: Optional[date_cls] = Query(None, alias="tu_ngay"),
    den: Optional[date_cls] = Query(None, alias="den_ngay"),
):
    """P&L summary trong khoảng [tu_ngay, den_ngay].

    Bao gồm cross-app: lương HCNS (theo tháng end-of-range),
    đơn hàng Mua Hàng, ads Marketing.

    Sprint W12: thêm breakdown by phòng_ban / quỹ / kênh / loại_thanh_toán.
    """
    tu, den = _resolve_range(tu, den)
    # Redis cache 30s — summary tổng hợp đắt do cross-app reads.
    try:
        from ..main import cache_get_or_set as _cache_gos  # type: ignore
        key = f"ketoan:bao_cao:tong_hop:{tu.isoformat()}:{den.isoformat()}"
        data = _cache_gos(
            key, 30,
            lambda: _build_tong_hop(db, tu, den).model_dump(mode="json"),
        )
        return BaoCaoTongHopOut(**data)
    except Exception:
        return _build_tong_hop(db, tu, den)


def _build_tong_hop(
    db: Session, tu: date_cls, den: date_cls
) -> BaoCaoTongHopOut:
    """Tính BaoCaoTongHopOut full breakdown — share giữa GET /tong-hop và POST /snapshot."""
    dt_total, dt_count = sum_doanh_thu(db, tu, den)
    cpps_total, cpps_count = sum_chi_phi_phat_sinh(db, tu, den)
    cpcd_total, _ = sum_chi_phi_co_dinh(db, tu, den)

    thang_chot = den.strftime("%Y-%m")
    luong_total = read_luong_total(db, thang_chot)
    don_hang_total = read_don_hang_total(db, tu, den)
    ads_total = read_ads_total(db, tu, den)

    tong_chi_phi = cpps_total + cpcd_total + luong_total + ads_total
    loi_nhuan_gop = (dt_total + don_hang_total) - cpps_total - cpcd_total
    loi_nhuan_truoc_thue = (dt_total + don_hang_total) - tong_chi_phi

    # ---------- Breakdown ----------
    # chi_phi by phong_ban (ORM, không cần fail-soft)
    cp_pb_rows = db.execute(
        select(
            func.coalesce(ChiPhiPhatSinh.phong_ban, "Khác"),
            func.coalesce(func.sum(ChiPhiPhatSinh.so_tien), 0),
        )
        .where(ChiPhiPhatSinh.ngay >= tu, ChiPhiPhatSinh.ngay <= den)
        .group_by(ChiPhiPhatSinh.phong_ban)
        .order_by(func.sum(ChiPhiPhatSinh.so_tien).desc())
    ).all()
    chi_phi_by_phong_ban = {str(k): float(v or 0) for k, v in cp_pb_rows}

    # chi_phi by quy
    cp_q_rows = db.execute(
        select(
            func.coalesce(ChiPhiPhatSinh.quy, "Khác"),
            func.coalesce(func.sum(ChiPhiPhatSinh.so_tien), 0),
        )
        .where(ChiPhiPhatSinh.ngay >= tu, ChiPhiPhatSinh.ngay <= den)
        .group_by(ChiPhiPhatSinh.quy)
        .order_by(func.sum(ChiPhiPhatSinh.so_tien).desc())
    ).all()
    chi_phi_by_quy = {str(k): float(v or 0) for k, v in cp_q_rows}

    # doanh_thu by loai_thanh_toan
    dt_ltt_rows = db.execute(
        select(
            func.coalesce(DoanhThu.loai_thanh_toan, "Khác"),
            func.coalesce(func.sum(DoanhThu.so_tien), 0),
        )
        .where(DoanhThu.ngay >= tu, DoanhThu.ngay <= den)
        .group_by(DoanhThu.loai_thanh_toan)
        .order_by(func.sum(DoanhThu.so_tien).desc())
    ).all()
    doanh_thu_by_loai_tt = {str(k): float(v or 0) for k, v in dt_ltt_rows}

    # cross-app fail-soft
    luong_by_phong_ban = _luong_by_phong_ban(db, thang_chot)
    ads_by_kenh = _ads_by_kenh(db, tu, den)

    return BaoCaoTongHopOut(
        tu_ngay=tu,
        den_ngay=den,
        tong_doanh_thu=dt_total,
        so_phieu_thu=dt_count,
        tong_chi_phi_phat_sinh=cpps_total,
        tong_chi_phi_co_dinh=cpcd_total,
        so_phieu_chi=cpps_count,
        tong_luong_hcns=luong_total,
        tong_ads_marketing=ads_total,
        tong_don_hang_muahang=don_hang_total,
        tong_chi_phi=tong_chi_phi,
        loi_nhuan_gop=loi_nhuan_gop,
        loi_nhuan_truoc_thue=loi_nhuan_truoc_thue,
        luong_by_phong_ban=luong_by_phong_ban,
        chi_phi_by_phong_ban=chi_phi_by_phong_ban,
        chi_phi_by_quy=chi_phi_by_quy,
        ads_by_kenh=ads_by_kenh,
        doanh_thu_by_loai_tt=doanh_thu_by_loai_tt,
    )


@router.get("/doanh-thu", response_model=list[GroupedAmount])
def bao_cao_doanh_thu(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu: Optional[date_cls] = Query(None, alias="tu_ngay"),
    den: Optional[date_cls] = Query(None, alias="den_ngay"),
    by: str = Query("ngay", pattern="^(ngay|thang)$"),
):
    """Doanh thu group by ngày hoặc tháng."""
    tu, den = _resolve_range(tu, den)

    def _compute():
        rows = group_by_date_doanh_thu(db, tu, den, by=by)
        return [
            GroupedAmount(key=k, so_tien=s, so_phieu=c).model_dump(mode="json")
            for k, s, c in rows
        ]

    try:
        from ..main import cache_get_or_set as _cache_gos  # type: ignore
        key = f"ketoan:bao_cao:doanh_thu:{by}:{tu.isoformat()}:{den.isoformat()}"
        data = _cache_gos(key, 30, _compute)
        return [GroupedAmount(**d) for d in data]
    except Exception:
        rows = group_by_date_doanh_thu(db, tu, den, by=by)
        return [GroupedAmount(key=k, so_tien=s, so_phieu=c) for k, s, c in rows]


@router.get("/chi-phi", response_model=list[GroupedAmount])
def bao_cao_chi_phi(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu: Optional[date_cls] = Query(None, alias="tu_ngay"),
    den: Optional[date_cls] = Query(None, alias="den_ngay"),
):
    """Chi phí phát sinh group by loại."""
    tu, den = _resolve_range(tu, den)

    def _compute():
        rows = group_by_loai_chi_phi(db, tu, den)
        return [
            GroupedAmount(key=k, so_tien=s, so_phieu=c).model_dump(mode="json")
            for k, s, c in rows
        ]

    try:
        from ..main import cache_get_or_set as _cache_gos  # type: ignore
        key = f"ketoan:bao_cao:chi_phi:{tu.isoformat()}:{den.isoformat()}"
        data = _cache_gos(key, 30, _compute)
        return [GroupedAmount(**d) for d in data]
    except Exception:
        rows = group_by_loai_chi_phi(db, tu, den)
        return [GroupedAmount(key=k, so_tien=s, so_phieu=c) for k, s, c in rows]


def _build_bao_cao_cong_no(
    db: Session, tu: date_cls, den: date_cls
) -> BaoCaoCongNoOut:
    pt_total, pt_count = sum_cong_no_by_loai(db, "phai_thu", tu, den, chua_tra_only=True)
    pp_total, pp_count = sum_cong_no_by_loai(db, "phai_tra", tu, den, chua_tra_only=True)

    rows = db.execute(
        select(
            CongNo.doi_tac,
            func.coalesce(func.sum(CongNo.con_lai), 0),
            func.count(CongNo.id),
        )
        .where(CongNo.trang_thai == "chua_tra")
        .where(CongNo.ngay >= tu, CongNo.ngay <= den)
        .group_by(CongNo.doi_tac)
        .order_by(func.sum(CongNo.con_lai).desc())
        .limit(50)
    ).all()

    return BaoCaoCongNoOut(
        tu_ngay=tu,
        den_ngay=den,
        tong_phai_thu=pt_total,
        tong_phai_tra=pp_total,
        so_no_phai_thu=pt_count,
        so_no_phai_tra=pp_count,
        by_doi_tac=[
            GroupedAmount(key=d or "Khác", so_tien=Decimal(s or 0), so_phieu=int(c or 0))
            for d, s, c in rows
        ],
    )


@router.get("/cong-no", response_model=BaoCaoCongNoOut)
def bao_cao_cong_no(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu: Optional[date_cls] = Query(None, alias="tu_ngay"),
    den: Optional[date_cls] = Query(None, alias="den_ngay"),
):
    """Tổng phải thu / phải trả còn lại (chưa trả)."""
    tu, den = _resolve_range(tu, den)
    try:
        from ..main import cache_get_or_set as _cache_gos  # type: ignore
        key = f"ketoan:bao_cao:cong_no:{tu.isoformat()}:{den.isoformat()}"
        data = _cache_gos(
            key, 30,
            lambda: _build_bao_cao_cong_no(db, tu, den).model_dump(mode="json"),
        )
        return BaoCaoCongNoOut(**data)
    except Exception:
        return _build_bao_cao_cong_no(db, tu, den)


# ---------------- /per-nv ----------------

@router.get("/per-nv")
def bao_cao_per_nv(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu: Optional[date_cls] = Query(None),
    den: Optional[date_cls] = Query(None),
):
    """Doanh số per NV từ `baogia.quotes` (raw SQL fail-soft). Trả {} nếu schema chưa có."""
    tu, den = _resolve_range(tu, den)
    data = _doanh_so_per_nv(db, tu, den)
    return {
        "tu_ngay": str(tu),
        "den_ngay": str(den),
        "data": data,                                      # {nv: tong_don}
        "tong": float(sum(data.values())),
    }


# ---------------- /snapshot/{thang} ----------------

def _parse_thang(thang: str) -> date_cls:
    """'YYYY-MM' (or 'YYYY-MM-DD') → date(YYYY, MM, 1)."""
    try:
        if len(thang) == 7:
            return datetime.strptime(thang + "-01", "%Y-%m-%d").date()
        return datetime.strptime(thang[:10], "%Y-%m-%d").date().replace(day=1)
    except ValueError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Tham số thang phải dạng YYYY-MM, nhận: {thang!r}",
        )


def _month_range(thang_date: date_cls) -> tuple[date_cls, date_cls]:
    """Trả (first_day, last_day) cho tháng `thang_date`."""
    if thang_date.month == 12:
        next_first = thang_date.replace(year=thang_date.year + 1, month=1, day=1)
    else:
        next_first = thang_date.replace(month=thang_date.month + 1, day=1)
    from datetime import timedelta
    last_day = next_first - timedelta(days=1)
    return thang_date, last_day


@router.get("/snapshot/{thang}")
def get_snapshot(
    thang: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Lấy snapshot đã lưu (404 nếu chưa có)."""
    thang_date = _parse_thang(thang)
    snap = db.execute(
        select(BaoCaoSnapshot).where(BaoCaoSnapshot.thang == thang_date)
    ).scalar_one_or_none()
    if not snap:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Snapshot tháng {thang!r} chưa tồn tại"
        )
    return {
        "id": snap.id,
        "thang": str(snap.thang),
        "data": snap.data,
        "created_at": snap.created_at.isoformat(),
        "created_by": snap.created_by,
    }


@router.post("/snapshot/{thang}", status_code=status.HTTP_201_CREATED)
def post_snapshot(
    thang: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Build P&L tổng hợp cho `thang` (full month) + lưu vào bao_cao_snapshot.data.

    Update (overwrite data) nếu đã tồn tại.
    """
    thang_date = _parse_thang(thang)
    tu, den = _month_range(thang_date)

    tong_hop = _build_tong_hop(db, tu, den)
    # Pydantic v2 dump → JSON-safe (Decimal → str). Chuyển sang dict an toàn cho JSONB.
    data: dict[str, Any] = tong_hop.model_dump(mode="json")

    snap = db.execute(
        select(BaoCaoSnapshot).where(BaoCaoSnapshot.thang == thang_date)
    ).scalar_one_or_none()

    action: str
    if snap:
        snap.data = data
        snap.created_by = user.username           # ai chốt cuối
        action = "update_snapshot"
    else:
        snap = BaoCaoSnapshot(
            thang=thang_date, data=data, created_by=user.username
        )
        db.add(snap)
        action = "create_snapshot"

    db.commit()
    db.refresh(snap)

    log_action(
        db, app="ketoan", action=action, user=user, request=request,
        resource=f"bao_cao_snapshot:{snap.id}",
        payload={"thang": str(thang_date)},
    )

    return {
        "id": snap.id,
        "thang": str(snap.thang),
        "data": snap.data,
        "created_at": snap.created_at.isoformat(),
        "created_by": snap.created_by,
    }
