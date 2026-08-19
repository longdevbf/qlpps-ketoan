"""External cross-schema reads — đọc hcns / muahang / marketing / baogia (READ-ONLY).

Không sửa code 4 app khác. Dùng raw SQL để fail-soft khi schema chưa khớp.
"""
import json
from datetime import date as date_cls, datetime
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


def _safe_rows(db: Session, sql: str, **params) -> list[dict[str, Any]]:
    """Execute query trả list dict. Fail-soft trả [] nếu bảng chưa tồn tại."""
    try:
        rows = db.execute(text(sql), params).mappings().all()
        return [dict(r) for r in rows]
    except (ProgrammingError, OperationalError) as e:
        db.rollback()
        return [{"_error": str(e)[:200]}]


def _safe_rows_silent(db: Session, sql: str, **params) -> list[dict[str, Any]]:
    """Như _safe_rows nhưng nuốt error → trả [] (dùng cho dropdown helper)."""
    try:
        rows = db.execute(text(sql), params).mappings().all()
        return [dict(r) for r in rows]
    except (ProgrammingError, OperationalError):
        db.rollback()
        return []


# -------------------- BHXH (HCNS) --------------------

@router.get("/bhxh")
def get_bhxh_external(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    trang_thai: Optional[str] = Query("Đang đóng", description="Lọc trạng thái; '' = tất cả"),
):
    """Danh sách BHXH + TỔNG tiền đóng (đọc hcns.bhxh, READ-ONLY) để kế toán nắm
    tổng phải nộp cơ quan BHXH = NLĐ (10.5%, trừ lương NV) + NSDLĐ (21.5%, công ty đóng).
    NSDLĐ là CHI PHÍ công ty; NLĐ đã trừ vào lương (bhxh_tru ở bảng lương)."""
    where = ""
    params: dict[str, Any] = {}
    st = (trang_thai or "").strip()
    if st:
        where = "WHERE trang_thai = :st"
        params["st"] = st
    sql = f"""
        SELECT ma_nv, ho_ten, phong_ban, chuc_vu, muc_dong, trang_thai,
               COALESCE(luong_dong,0)  AS luong_dong,
               COALESCE(nld_bhxh,0)    AS nld_bhxh,   COALESCE(nld_bhyt,0)   AS nld_bhyt,
               COALESCE(nld_bhtn,0)    AS nld_bhtn,   COALESCE(nld_tong,0)   AS nld_tong,
               COALESCE(nsdld_bhxh,0)  AS nsdld_bhxh, COALESCE(nsdld_bhyt,0) AS nsdld_bhyt,
               COALESCE(nsdld_bhtn,0)  AS nsdld_bhtn, COALESCE(nsdld_tong,0) AS nsdld_tong
        FROM hcns.bhxh
        {where}
        ORDER BY phong_ban NULLS LAST, ho_ten
    """
    rows = _safe_rows(db, sql, **params)
    if rows and rows[0].get("_error"):
        return {"data": [], "totals": {}, "error": rows[0]["_error"]}

    def _f(x):
        try:
            return float(x or 0)
        except Exception:
            return 0.0
    _NUM = ("luong_dong", "nld_bhxh", "nld_bhyt", "nld_bhtn", "nld_tong",
            "nsdld_bhxh", "nsdld_bhyt", "nsdld_bhtn", "nsdld_tong")
    data: list[dict[str, Any]] = []
    T: dict[str, Any] = {"so_nv": 0}
    for k in _NUM:
        T[k] = 0.0
    for r in rows:
        item = {
            "ma_nv": r.get("ma_nv"), "ho_ten": r.get("ho_ten"),
            "phong_ban": r.get("phong_ban"), "chuc_vu": r.get("chuc_vu"),
            "muc_dong": r.get("muc_dong"), "trang_thai": r.get("trang_thai"),
        }
        for k in _NUM:
            v = _f(r.get(k))
            item[k] = v
            T[k] += v
        item["tong"] = item["nld_tong"] + item["nsdld_tong"]  # tổng nộp của NV này
        data.append(item)
        T["so_nv"] += 1
    T["tong_nop"] = T["nld_tong"] + T["nsdld_tong"]  # tổng phải nộp cơ quan BHXH
    return {"data": data, "totals": T, "trang_thai": st or "Tất cả"}


# -------------------- LƯƠNG (HCNS) --------------------

@router.get("/luong")
def get_luong_external(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    thang: Optional[str] = Query(None, description="'YYYY-MM' — default: tháng hiện tại"),
):
    """Bảng lương LIVE từ HCNS — gọi thẳng compute `bang_luong_thang`.

    2026-07-02 (anh Quang): HCNS tính lương LIVE (từ nhân sự + chấm công +
    cơ chế), KHÔNG persist xuống `hcns.payroll` (bảng đó rỗng). Trước đây kế toán
    đọc bảng rỗng → Bảng Lương HCNS trống ("chưa đồng bộ"). Nay đọc thẳng compute
    của HCNS để luôn khớp. Fail-soft: lỗi import/compute → fallback bảng cũ.
    """
    if not thang:
        thang = datetime.now().strftime("%Y-%m")
    try:
        from hcns.app.routers.payroll import bang_luong_thang  # cross-app, cùng process
        res = bang_luong_thang(user, db, thang)
        data = []
        for r in res.get("rows", []):
            data.append({
                **r,
                "thang": thang,
                # alias cho FE kế toán (cột BHXH / Thực Lãnh)
                "bhxh": r.get("bhxh_tru", 0),
                "luong_thuc_linh": r.get("luong_thuc_nhan", 0),
            })
        return {"thang": thang, "data": data, "source": "hcns_live"}
    except Exception:
        db.rollback()
        sql = """
            SELECT *
            FROM hcns.payroll
            WHERE thang = :thang
            ORDER BY phong_ban, ho_ten
            LIMIT 1000
        """
        return {"thang": thang, "data": _safe_rows(db, sql, thang=thang), "source": "table_fallback"}


# -------------------- DON HANG (Mua Hàng) --------------------

@router.get("/don-hang")
def get_don_hang_external(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu_ngay: Optional[date_cls] = Query(None),
    den_ngay: Optional[date_cls] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """Đọc đơn mua hàng từ `muahang.purchase_orders`."""
    today = date_cls.today()
    if not den_ngay:
        den_ngay = today
    if not tu_ngay:
        tu_ngay = today.replace(day=1)

    sql = """
        SELECT id, ten_don, status, ref_bao_gia, nv_mua_hang, selected_ncc_id,
               discount, ncc_totals, created_at, ngay_dat_xuong
        FROM muahang.purchase_orders
        WHERE created_at::date >= :tu AND created_at::date <= :den
    """
    params: dict[str, Any] = {"tu": tu_ngay, "den": den_ngay}
    if status_filter:
        sql += " AND status = :st"
        params["st"] = status_filter
    sql += " ORDER BY created_at DESC LIMIT 500"
    return {
        "tu_ngay": str(tu_ngay), "den_ngay": str(den_ngay),
        "data": _safe_rows(db, sql, **params),
    }


# -------------------- ADS (Marketing) --------------------

@router.get("/ads")
def get_ads_external(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu_ngay: Optional[date_cls] = Query(None),
    den_ngay: Optional[date_cls] = Query(None),
    kenh: Optional[str] = None,
):
    """Đọc chi phí ads từ `marketing.ads_cost`."""
    today = date_cls.today()
    if not den_ngay:
        den_ngay = today
    if not tu_ngay:
        tu_ngay = today.replace(day=1)

    sql = """
        SELECT id, thang, ngay, kenh, san_pham, chi_phi, so_inbox, so_data,
               nguoi_nhap, created_at
        FROM marketing.ads_cost
        WHERE ngay >= :tu AND ngay <= :den
    """
    params: dict[str, Any] = {"tu": tu_ngay, "den": den_ngay}
    if kenh:
        sql += " AND kenh = :kenh"
        params["kenh"] = kenh
    sql += " ORDER BY ngay DESC LIMIT 500"
    return {
        "tu_ngay": str(tu_ngay), "den_ngay": str(den_ngay),
        "data": _safe_rows(db, sql, **params),
    }


# ============================================================================
# Issue 3 — Cross-app dropdown helpers (NV / phòng ban / ads campaigns / quotes)
# ============================================================================

# -------------------- EMPLOYEES (HCNS) --------------------

@router.get("/employees")
def list_employees_external(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    q: Optional[str] = Query(None, description="Tìm theo ho_ten/ma_nv (ILIKE)"),
    active: bool = Query(True, description="Chỉ NV đang làm (trang_thai='Đang làm')"),
    phong_ban: Optional[str] = Query(None),
):
    """Dropdown helper — list NV active từ hcns.employees.

    NOTE: hcns.employees PK = ma_nv (string). Trả `id` = digit-only suffix
    để map vào ketoan.so_quy.nhan_vien_id (Integer). Nếu ma_nv không có
    số → id = None.
    """
    sql = """
        SELECT ma_nv, ho_ten, phong_ban, chuc_vu, trang_thai
        FROM hcns.employees
        WHERE 1=1
    """
    params: dict[str, Any] = {}
    if active:
        sql += " AND COALESCE(trang_thai, 'Đang làm') = 'Đang làm'"
    if phong_ban:
        sql += " AND phong_ban = :pb"
        params["pb"] = phong_ban
    if q:
        sql += " AND (ho_ten ILIKE :kw OR ma_nv ILIKE :kw)"
        params["kw"] = f"%{q.strip()}%"
    sql += " ORDER BY phong_ban NULLS LAST, ho_ten LIMIT 200"
    rows = _safe_rows_silent(db, sql, **params)
    # Enrich `id` từ ma_nv: 'NV26015' → 26015
    for r in rows:
        ma = (r.get("ma_nv") or "").strip()
        digits = "".join(c for c in ma if c.isdigit())
        r["id"] = int(digits) if digits else None
    return {"data": rows}


# -------------------- DEPARTMENTS (HCNS) --------------------

@router.get("/departments")
def list_departments_external(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Dropdown helper — phòng ban (UNION từ employees + departments).

    Trả [{ten_phong_ban, so_nv}, ...] — top 50.
    """
    # Try employees first (chắc chắn có)
    sql_emp = """
        SELECT phong_ban AS ten_phong_ban, COUNT(*)::int AS so_nv
        FROM hcns.employees
        WHERE phong_ban IS NOT NULL AND phong_ban != ''
              AND COALESCE(trang_thai, 'Đang làm') = 'Đang làm'
        GROUP BY phong_ban
    """
    emp_rows = _safe_rows_silent(db, sql_emp)
    pb_map: dict[str, int] = {
        (r.get("ten_phong_ban") or "").strip(): int(r.get("so_nv") or 0)
        for r in emp_rows if r.get("ten_phong_ban")
    }

    # UNION với hcns.departments (nếu tồn tại) — fallback nếu schema khác
    sql_dep = """
        SELECT ten_phong_ban
        FROM hcns.departments
    """
    dep_rows = _safe_rows_silent(db, sql_dep)
    for r in dep_rows:
        name = (r.get("ten_phong_ban") or "").strip()
        if name and name not in pb_map:
            pb_map[name] = 0

    out = [
        {"ten_phong_ban": k, "so_nv": v}
        for k, v in sorted(pb_map.items(), key=lambda kv: (-kv[1], kv[0]))
    ][:50]
    return {"data": out}


# -------------------- ADS CAMPAIGNS (Marketing) --------------------

@router.get("/ads-campaigns")
def list_ads_campaigns_external(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    thang: Optional[str] = Query(None, description="'YYYY-MM' filter"),
    kenh: Optional[str] = Query(None),
):
    """Dropdown helper — chiến dịch ads (group from ads_cost + fallback ads_campaign).

    Top 100, fail-soft.
    """
    out: list[dict[str, Any]] = []

    # Primary: group ads_cost theo (thang, kenh, san_pham)
    sql_cost = """
        SELECT thang, kenh,
               COALESCE(MAX(san_pham), '') AS ten_chien_dich,
               COALESCE(SUM(chi_phi), 0)   AS tong_chi_phi,
               COUNT(*)::int                AS so_dong
        FROM marketing.ads_cost
        WHERE 1=1
    """
    params: dict[str, Any] = {}
    if thang:
        sql_cost += " AND thang = :thang"
        params["thang"] = thang
    if kenh:
        sql_cost += " AND kenh = :kenh"
        params["kenh"] = kenh
    sql_cost += """
        GROUP BY thang, kenh
        ORDER BY thang DESC, kenh
        LIMIT 100
    """
    out.extend(_safe_rows_silent(db, sql_cost, **params))

    # Fallback: marketing.ads_campaign nếu tồn tại
    if not out:
        sql_camp = """
            SELECT id, ten_chien_dich, kenh, status
            FROM marketing.ads_campaign
        """
        cparams: dict[str, Any] = {}
        if kenh:
            sql_camp += " WHERE kenh = :kenh"
            cparams["kenh"] = kenh
        sql_camp += " ORDER BY id DESC LIMIT 100"
        out = _safe_rows_silent(db, sql_camp, **cparams)

    return {"data": out}


# -------------------- QUOTES LIST (BaoGia) --------------------

@router.get("/quotes-list")
def list_quotes_external(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    status_filter: Optional[str] = Query("approved", alias="status"),
    q: Optional[str] = Query(None, description="Tìm quote_number/customer_name"),
    tu_ngay: Optional[date_cls] = Query(None, alias="from"),
    den_ngay: Optional[date_cls] = Query(None, alias="to"),
):
    """Dropdown helper — báo giá từ baogia.quotes.

    Schema baogia V2: id, quote_number (= ma_bg), customer_name, tong_don,
    status, duyet_status, duyet_luc, salesperson (= nv_kd).
    """
    sql = """
        SELECT id,
               quote_number AS ma_bg,
               customer_name,
               tong_don,
               status,
               duyet_status,
               duyet_luc,
               salesperson AS nv_kd,
               created_at
        FROM baogia.quotes
        WHERE 1=1
    """
    params: dict[str, Any] = {}
    if status_filter:
        s = status_filter.strip().lower()
        if s in ("approved", "duyet", "da_duyet"):
            sql += " AND COALESCE(duyet_status, '') IN ('approved', 'da_duyet')"
        elif s in ("all", "*", ""):
            pass
        else:
            sql += " AND COALESCE(status, '') = :st"
            params["st"] = status_filter
    if q:
        sql += " AND (quote_number ILIKE :kw OR customer_name ILIKE :kw)"
        params["kw"] = f"%{q.strip()}%"
    if tu_ngay:
        sql += " AND COALESCE(duyet_luc::date, created_at::date) >= :tu"
        params["tu"] = tu_ngay
    if den_ngay:
        sql += " AND COALESCE(duyet_luc::date, created_at::date) <= :den"
        params["den"] = den_ngay
    sql += " ORDER BY COALESCE(duyet_luc, created_at) DESC NULLS LAST LIMIT 100"
    return {"data": _safe_rows_silent(db, sql, **params)}


# ============================================================================
# WORKFLOW: Đối chiếu thu/chi đơn hàng đã giao → chuyển sang Hoàn Thành
# ============================================================================

def _sp_identity_map(db: Session) -> dict[str, str]:
    """Map mọi alias (username | full_name | ho_ten — đã lower) -> ho_ten CHUẨN (HCNS ưu tiên).

    Dùng gộp các biến thể `salesperson` trong báo giá (mã nv26010, tên đầy đủ,
    tên ngắn...) về cùng 1 nhân viên cho dropdown + filter Đơn Hàng.
    """
    m: dict[str, str] = {}
    user_to_full: dict[str, str] = {}
    for r in _safe_rows_silent(db, """
        SELECT username, full_name FROM shared.users
        WHERE username IS NOT NULL AND full_name IS NOT NULL
    """):
        u = (r.get("username") or "").strip()
        fn = (r.get("full_name") or "").strip()
        if u and fn:
            user_to_full[u.lower()] = fn
            m[u.lower()] = fn
        if fn:
            m.setdefault(fn.lower(), fn)
    for r in _safe_rows_silent(db, """
        SELECT username, ho_ten FROM hcns.employees
        WHERE username IS NOT NULL AND ho_ten IS NOT NULL
    """):
        u = (r.get("username") or "").strip()
        ht = (r.get("ho_ten") or "").strip()
        if u and ht:
            m[u.lower()] = ht          # mã nv -> ho_ten (ưu tiên HCNS)
            m[ht.lower()] = ht         # ho_ten self-map
            fn = user_to_full.get(u.lower())
            if fn and fn.lower() != ht.lower():
                m[fn.lower()] = ht     # full_name -> ho_ten
    return m


def _canon_sp(raw: Optional[str], idmap: dict[str, str]) -> str:
    """Trả tên chuẩn của 1 giá trị salesperson; không khớp employee thì giữ nguyên."""
    k = (raw or "").strip().lower()
    return idmap.get(k, (raw or "").strip())


@router.get("/orders-salespeople")
def orders_salespeople(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """List NV KD từ baogia.quotes (đơn approved) — GỘP biến thể (mã nv / tên) về
    cùng 1 nhân viên theo ho_ten chuẩn, cộng dồn số đơn."""
    rows = _safe_rows_silent(db, """
        SELECT TRIM(salesperson) AS name, COUNT(*) AS so_don
        FROM baogia.quotes
        WHERE duyet_status = 'approved'
          AND salesperson IS NOT NULL
          AND TRIM(salesperson) <> ''
        GROUP BY TRIM(salesperson)
    """)
    idmap = _sp_identity_map(db)
    merged: dict[str, dict] = {}
    for r in rows:
        canon = _canon_sp(r.get("name"), idmap)
        slot = merged.setdefault(canon.lower(), {"name": canon, "so_don": 0})
        slot["so_don"] += int(r.get("so_don") or 0)
    data = sorted(merged.values(), key=lambda x: x["name"].lower())
    return {"data": data}


@router.get("/orders-overview")
def orders_overview(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    filter: str = Query("active", description="active|pending|done|all"),
    salesperson: Optional[str] = Query(None, description="Lọc NV KD (q.salesperson, case-insensitive)"),
):
    """Bảng đối chiếu kế toán — overview mỗi đơn báo giá đã duyệt.

    `filter`:
      - `active`:  đơn duyệt + CHƯA Hoàn Thành (case-insensitive trim — bắt cả 'hoàn thành' lowercase)
      - `pending`: vc.trang_thai='da_giao' chờ kế toán đối chiếu
      - `done`:    đã xong - kế toán đã đối chiếu (vc.ketoan_approved_at IS NOT NULL)
      - `all`:     tất cả đơn duyệt

    `salesperson` (optional): filter NV KD, exact match case/space-insensitive.

    (Bỏ filter 'completed' vì trùng với 'done' về mặt nghiệp vụ — 'done' subset của
    completed, mà KT chỉ quan tâm 2 trạng thái: đã đối chiếu vs chưa đối chiếu.)
    """
    where_clause = "q.duyet_status = 'approved'"
    if filter == "pending":
        where_clause = "v.trang_thai = 'da_giao'"
    elif filter == "done":
        where_clause = "q.duyet_status = 'approved' AND v.ketoan_approved_at IS NOT NULL"
    elif filter == "active":
        # Case/space-insensitive — bắt mọi biến thể: 'Hoàn Thành', 'Hoàn thành',
        # 'hoàn thành', ' Hoàn Thành ' → đều loại khỏi 'active'.
        where_clause = (
            "q.duyet_status = 'approved' "
            "AND LOWER(TRIM(COALESCE(q.tien_trinh_mh, ''))) <> 'hoàn thành'"
        )

    if salesperson:
        # Dropdown trả ho_ten chuẩn → khớp MỌI biến thể salesperson (mã nv, tên
        # đầy đủ, tên ngắn) gộp về cùng nhân viên đó.
        idmap = _sp_identity_map(db)
        target = _canon_sp(salesperson, idmap).lower()
        raw_rows = _safe_rows_silent(db, """
            SELECT DISTINCT TRIM(salesperson) AS s FROM baogia.quotes
            WHERE salesperson IS NOT NULL AND TRIM(salesperson) <> ''
        """)
        aliases = [r["s"] for r in raw_rows if _canon_sp(r.get("s"), idmap).lower() == target]
        if not aliases:
            aliases = [salesperson.strip()]
        in_list = ", ".join("'" + a.replace("'", "''").lower() + "'" for a in aliases)
        where_clause += f" AND LOWER(TRIM(COALESCE(q.salesperson,''))) IN ({in_list})"

    sql = f"""
        WITH doanh_thu_agg AS (
            -- Tổng thu theo mã đơn, tách Đặt Cọc / Thanh Toán / tổng
            SELECT ma_don,
                   SUM(so_tien) AS thu_thuc,
                   SUM(CASE WHEN loai_thanh_toan = 'Đặt cọc'   THEN so_tien ELSE 0 END) AS thu_dat_coc,
                   SUM(CASE WHEN loai_thanh_toan = 'Thanh toán' THEN so_tien ELSE 0 END) AS thu_thanh_toan
            FROM ketoan.doanh_thu
            WHERE ma_don IS NOT NULL
            GROUP BY ma_don
        ),
        cong_no_agg AS (
            SELECT ma_don,
                   SUM(CASE WHEN loai='phai_thu' THEN so_tien ELSE 0 END) AS cn_phai_thu,
                   SUM(CASE WHEN loai='phai_thu' THEN da_tra ELSE 0 END) AS cn_da_thu,
                   SUM(CASE WHEN loai='phai_tra' THEN so_tien ELSE 0 END) AS cn_phai_tra,
                   SUM(CASE WHEN loai='phai_tra' THEN da_tra ELSE 0 END) AS cn_da_tra
            FROM ketoan.cong_no WHERE ma_don IS NOT NULL GROUP BY ma_don
        ),
        po_agg AS (
            SELECT ref_bao_gia,
                   COUNT(*) AS so_po,
                   STRING_AGG(DISTINCT status, ', ') AS po_statuses,
                   MAX(id) AS last_po_id
            FROM muahang.purchase_orders
            WHERE ref_bao_gia IS NOT NULL
            GROUP BY ref_bao_gia
        ),
        cmt_agg AS (
            -- Tin nhắn cross-app trên đơn: marketing.lead_comments có prefix `[BG <ma_bg>] ...`
            -- → đếm + lấy thời điểm comment mới nhất theo từng đơn.
            SELECT q2.quote_number AS ma_bg,
                   COUNT(*) AS comment_count,
                   MAX(lc.thoi_gian) AS last_comment_at
            FROM marketing.lead_comments lc
            JOIN baogia.customers c2 ON c2.lead_id = lc.lead_id
            JOIN baogia.quotes     q2 ON q2.customer_id = c2.id
            WHERE lc.noi_dung ILIKE '[BG ' || q2.quote_number || ']%'
            GROUP BY q2.quote_number
        )
        SELECT
            -- ĐƠN
            q.quote_number AS ma_bg, q.customer_name, q.customer_phone,
            q.salesperson, q.created_at AS ngay_tao,
            COALESCE(q.duyet_luc, q.created_at) AS ngay_duyet,
            q.tong_don, q.deposit, q.tien_thue,

            -- TIẾN TRÌNH
            q.duyet_status AS bg_status,
            q.tien_trinh_mh,
            v.ma_vh, v.trang_thai AS vc_status, v.ngay_giao,
            v.don_vi_vc,
            v.ketoan_approved_at, v.ketoan_approved_by,
            (COALESCE((SELECT MAX((e->>'ts')::timestamp) FROM jsonb_array_elements(COALESCE(v.tien_trinh,'[]'::jsonb)) e WHERE e->>'stage'='hoan_sla'), '1900-01-01'::timestamp)
             > COALESCE((SELECT MAX((e->>'ts')::timestamp) FROM jsonb_array_elements(COALESCE(v.tien_trinh,'[]'::jsonb)) e WHERE e->>'stage'='bo_hoan_sla'), '1900-01-01'::timestamp)
            ) AS sla_hoan,
            COALESCE(po.po_statuses, '—') AS po_status,
            COALESCE(po.so_po, 0) AS so_po,

            -- PHẢI THU
            COALESCE(dta.thu_thuc, 0)       AS thu_thuc_te,
            COALESCE(dta.thu_dat_coc, 0)    AS thu_dat_coc,
            COALESCE(dta.thu_thanh_toan, 0) AS thu_thanh_toan,
            COALESCE(cn.cn_phai_thu, 0) AS cn_phai_thu,
            COALESCE(cn.cn_da_thu, 0) AS cn_da_thu,

            -- PHẢI TRẢ
            COALESCE(cn.cn_phai_tra, 0) AS cn_phai_tra,
            COALESCE(cn.cn_da_tra, 0) AS cn_da_tra,
            v.chi_phi_vc, v.da_tra_dvvc, v.tien_thu_ho, v.dvvc_da_thu,

            -- TIN NHẮN
            COALESCE(cmt.comment_count, 0) AS comment_count,
            cmt.last_comment_at

        FROM baogia.quotes q
        -- LATERAL JOIN: 1 báo giá có thể có NHIỀU lệnh vận chuyển (giao nhiều đợt).
        -- Để tránh đơn hàng hiển thị TRÙNG, chỉ lấy lệnh VC mới nhất per quote.
        LEFT JOIN LATERAL (
            SELECT ma_vh, trang_thai, ngay_giao, don_vi_vc, tien_trinh,
                   ketoan_approved_at, ketoan_approved_by,
                   chi_phi_vc, da_tra_dvvc, tien_thu_ho, dvvc_da_thu
            FROM saleadmin.vanchuyen
            WHERE ma_don = q.quote_number
            ORDER BY created_at DESC LIMIT 1
        ) v ON TRUE
        LEFT JOIN po_agg po ON po.ref_bao_gia = q.quote_number
        LEFT JOIN doanh_thu_agg dta ON dta.ma_don = q.quote_number
        LEFT JOIN cong_no_agg cn ON cn.ma_don = q.quote_number
        LEFT JOIN cmt_agg cmt ON cmt.ma_bg = q.quote_number
        WHERE {where_clause}
        ORDER BY q.created_at DESC
        LIMIT 200
    """
    return {"filter": filter, "data": _safe_rows(db, sql)}


@router.get("/orders-optimization")
def orders_optimization(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu_ngay: Optional[date_cls] = Query(None),
    den_ngay: Optional[date_cls] = Query(None),
    salesperson: Optional[str] = Query(None, description="Lọc NV KD (canonical, case-insensitive)"),
    max_ck: float = Query(20.0, description="Chính sách chiết khấu tối đa (%) — mặc định 20"),
):
    """Tab 'Tối ưu chiết khấu' — mỗi đơn báo giá đã duyệt.

    Chính sách: mỗi đơn được chiết khấu tối đa `max_ck`%. NV KD bán mà chiết khấu
    thực tế < max_ck% thì phần chưa dùng được quy ra tiền = "số tiền tối ưu".

    - CK thực tế = (giảm theo % + giảm số tiền tuyệt đối) / tạm_tính × 100
    - tạm_tính (trước CK, chưa thuế) suy ra từ header:
        chua_thue = tong_don − tien_thue
        tam_tinh  = (chua_thue + discount_amount) / (1 − discount_percent/100)
    - số_tiền_tối_ưu = (max_ck% × tam_tinh) − tổng_giảm
        (dương = giảm ít hơn mức tối đa → tốt; âm = VƯỢT chính sách)

    Cộng dồn theo NV KD làm cơ sở thưởng.
    """
    where = "q.duyet_status = 'approved'"
    params: dict[str, Any] = {}
    # Lọc theo THỜI ĐIỂM DUYỆT (duyet_luc) — khớp kỳ doanh số, không theo ngày tạo.
    if tu_ngay:
        where += " AND COALESCE(q.duyet_luc, q.created_at)::date >= :tu"
        params["tu"] = tu_ngay
    if den_ngay:
        where += " AND COALESCE(q.duyet_luc, q.created_at)::date <= :den"
        params["den"] = den_ngay
    if salesperson:
        # Lọc theo tên NV KD chuẩn (ho_ten HCNS suy từ mã NV ở prefix mã đơn)
        where += (
            " AND LOWER(TRIM(COALESCE(e.ho_ten,"
            " substring(q.quote_number from '^(NV[0-9]+)'), q.salesperson, ''))) = :sp"
        )
        params["sp"] = salesperson.strip().lower()

    # Tên NV KD = ho_ten HCNS map từ mã NV ở prefix mã báo giá (KHÔNG dùng text
    # salesperson gõ tay — vì text thường sai/thiếu, ví dụ nic Zalo 'Tuệ Nhiên').
    sql = f"""
        SELECT q.quote_number AS ma_bg, q.customer_name,
               COALESCE(e.ho_ten,
                        substring(q.quote_number from '^(NV[0-9]+)'),
                        NULLIF(TRIM(q.salesperson), ''),
                        '(không rõ)') AS salesperson,
               q.created_at AS ngay_tao,
               q.duyet_luc AS ngay_duyet,
               COALESCE(q.discount_percent, 0) AS discount_percent,
               COALESCE(q.discount_amount, 0)  AS discount_amount,
               COALESCE(q.tien_thue, 0)        AS tien_thue,
               COALESCE(q.tong_don, 0)         AS tong_don,
               c.loai_don, c.papasan_base
        FROM baogia.quotes q
        LEFT JOIN hcns.employees e
               ON LOWER(e.ma_nv) = LOWER(substring(q.quote_number from '^(NV[0-9]+)'))
        LEFT JOIN LATERAL (
            -- Loại đơn theo SP CHÍNH — KHỚP engine HCNS `co_che_toi_uu`:
            -- phụ kiện/dịch vụ trung lập; có gỗ → Gỗ; mây → Mây.
            -- GHẾ PAPASAN (anh Quang 2026-07-27): SP ghế Papasan MIỄN chính sách CK.
            -- `papasan_base` = tổng giá trị dòng ghế Papasan (trước CK) → Python tách:
            -- đơn TOÀN Papasan → 'Ghế Papasan' miễn; đơn PHA → 'Đồ Mây' nhưng chỉ tính
            -- trần 15% trên phần đồ mây khác (loại giá trị Papasan ra theo tỷ trọng).
            SELECT
              CASE
                WHEN bool_or(p.nhom_master = 'Đồ Gỗ')  THEN 'Đồ Gỗ'
                WHEN bool_or(p.nhom_master = 'Đồ Mây') THEN 'Đồ Mây'
                ELSE NULL
              END AS loai_don,
              COALESCE(SUM(COALESCE(qi.don_gia_tinh,0) * COALESCE(qi.so_luong,1))
                       FILTER (WHERE qi.product_type ILIKE '%papasan%'), 0) AS papasan_base
            FROM baogia.quote_items qi
            JOIN shared.products p ON p.ten_sp = qi.product_type
            WHERE qi.quote_id = q.id
              AND p.nhom_master IN ('Đồ Gỗ', 'Đồ Mây')
        ) c ON TRUE
        WHERE {where}
        ORDER BY COALESCE(q.duyet_luc, q.created_at) DESC
        LIMIT 1000
    """
    rows = _safe_rows(db, sql, **params)

    # CK TRẦN THEO LOẠI ĐƠN — lấy thẳng từ CƠ CHẾ HCNS (`co_che_toi_uu`) để số
    # luôn KHỚP HCNS: Đồ Gỗ 20% / Đồ Mây 15% (anh Quang 2026-07-15). Config có
    # hiệu lực theo tháng (không hồi tố) → dùng tháng của kỳ đang xem.
    _thang_cfg = (den_ngay or tu_ngay or date_cls.today()).strftime("%Y-%m")
    try:
        from hcns.app.services.co_che_toi_uu import load_config as _load_tu_cfg
        _cfg_tu = _load_tu_cfg(db, _thang_cfg)
        max_ck_go = float(_cfg_tu.get("max_ck_go", _cfg_tu.get("max_ck", max_ck)))
        max_ck_may = float(_cfg_tu.get("max_ck_may", 15.0))
    except Exception:
        max_ck_go, max_ck_may = float(max_ck), 15.0

    orders: list[dict[str, Any]] = []
    sp_agg: dict[str, dict[str, Any]] = {}
    T = {"so_don": 0, "tam_tinh": 0.0, "tong_giam": 0.0, "toi_uu": 0.0}
    # Tách tổng theo loại đơn (Đồ Mây / Đồ Gỗ)
    T_loai: dict[str, dict[str, Any]] = {}

    for r in rows:
        pct = float(r.get("discount_percent") or 0)
        amt = float(r.get("discount_amount") or 0)
        tien_thue = float(r.get("tien_thue") or 0)
        tong_don = float(r.get("tong_don") or 0)
        chua_thue = tong_don - tien_thue
        if pct < 100:
            tam_tinh = (chua_thue + amt) / (1 - pct / 100.0)
        else:
            tam_tinh = chua_thue + amt
        tam_tinh = max(0.0, tam_tinh)
        tong_giam = max(0.0, tam_tinh - chua_thue)

        # ── GHẾ PAPASAN — miễn chính sách chiết khấu (anh Quang 2026-07-27) ──
        # papasan_base = giá trị dòng ghế Papasan (trước CK). Tách phần đồ mây khác
        # CHỊU trần 15%; giảm giá phân bổ theo TỶ TRỌNG giá trị.
        loai_base = (r.get("loai_don") or "").strip() or None
        papasan_base = float(r.get("papasan_base") or 0)
        is_papasan = False       # đơn TOÀN ghế Papasan → miễn hẳn
        is_papasan_mix = False   # đơn PHA: Papasan + đồ mây khác
        if loai_base == "Đồ Mây" and papasan_base > 0 and tam_tinh > 0:
            eligible = tam_tinh - papasan_base   # phần đồ mây khác (chịu CK)
            if eligible < 1000.0:                # coi như toàn Papasan (chừa sai số)
                is_papasan = True
            else:
                is_papasan_mix = True

        if is_papasan:
            # Toàn Papasan: hiển thị nguyên đơn, tối ưu = 0.
            loai_don = "Ghế Papasan"; mck = 0.0
            so_tien_toi_uu = 0.0; toi_uu_pct = 0.0
            ck_pct_eff = (tong_giam / tam_tinh * 100.0) if tam_tinh > 0 else 0.0
            row_tam_tinh, row_tong_giam = tam_tinh, tong_giam
        elif is_papasan_mix:
            # Đơn pha: chỉ tính trần 15% trên phần đồ mây khác; giảm giá phân bổ
            # theo tỷ trọng. Row hiển thị theo phần đồ mây khác (badge "trừ Papasan").
            loai_don = "Đồ Mây"; mck = max_ck_may
            frac = max(0.0, min(1.0, eligible / tam_tinh))
            row_tam_tinh = eligible
            row_tong_giam = tong_giam * frac
            ck_pct_eff = (row_tong_giam / row_tam_tinh * 100.0) if row_tam_tinh > 0 else 0.0
            so_tien_toi_uu = (mck / 100.0) * row_tam_tinh - row_tong_giam
            toi_uu_pct = mck - ck_pct_eff
        else:
            loai_don = loai_base
            mck = max_ck_may if loai_base == "Đồ Mây" else max_ck_go
            ck_pct_eff = (tong_giam / tam_tinh * 100.0) if tam_tinh > 0 else 0.0
            so_tien_toi_uu = (mck / 100.0) * tam_tinh - tong_giam
            toi_uu_pct = mck - ck_pct_eff
            row_tam_tinh, row_tong_giam = tam_tinh, tong_giam
        sp_canon = (r.get("salesperson") or "(không rõ)")

        orders.append({
            "ma_bg": r.get("ma_bg"),
            "customer_name": r.get("customer_name"),
            "salesperson": sp_canon,
            "ngay_tao": r.get("ngay_tao"),
            "ngay_duyet": r.get("ngay_duyet"),
            "loai_don": loai_don or "Chưa phân loại",
            "is_papasan": is_papasan,
            "is_papasan_mix": is_papasan_mix,
            "papasan_base": round(papasan_base),
            "max_ck_ap_dung": mck,
            "tam_tinh": round(row_tam_tinh),
            "tong_giam": round(row_tong_giam),
            "ck_pct": round(ck_pct_eff, 2),
            "toi_uu_pct": round(toi_uu_pct, 2),
            "so_tien_toi_uu": round(so_tien_toi_uu),
            "vuot_chinh_sach": (so_tien_toi_uu < 0) and not is_papasan,
        })

        a = sp_agg.setdefault(sp_canon, {
            "salesperson": sp_canon, "so_don": 0,
            "tam_tinh": 0.0, "tong_giam": 0.0, "toi_uu": 0.0,
        })
        a["so_don"] += 1
        a["tam_tinh"] += row_tam_tinh
        a["tong_giam"] += row_tong_giam
        a["toi_uu"] += so_tien_toi_uu

        T["so_don"] += 1
        T["tam_tinh"] += row_tam_tinh
        T["tong_giam"] += row_tong_giam
        T["toi_uu"] += so_tien_toi_uu

        # Tách theo loại đơn. `toi_uu` = cộng có dấu (âm = vượt chính sách, giữ
        # nguyên nghĩa cũ của tab). `toi_uu_hcns` = CHỈ cộng đơn còn dư trần —
        # đúng cơ chế HCNS chia thưởng (engine bỏ qua đơn có tối ưu <= 0).
        L = T_loai.setdefault(loai_don or "Chưa phân loại", {
            "loai_don": loai_don or "Chưa phân loại", "max_ck": mck,
            "so_don": 0, "tam_tinh": 0.0, "tong_giam": 0.0,
            "toi_uu": 0.0, "toi_uu_hcns": 0.0,
        })
        L["so_don"] += 1
        L["tam_tinh"] += row_tam_tinh
        L["tong_giam"] += row_tong_giam
        L["toi_uu"] += so_tien_toi_uu
        if so_tien_toi_uu > 0:
            L["toi_uu_hcns"] += so_tien_toi_uu

    by_sp = []
    for a in sp_agg.values():
        ck_tb = (a["tong_giam"] / a["tam_tinh"] * 100.0) if a["tam_tinh"] > 0 else 0.0
        by_sp.append({
            "salesperson": a["salesperson"], "so_don": a["so_don"],
            "tam_tinh": round(a["tam_tinh"]), "ck_tb_pct": round(ck_tb, 2),
            "toi_uu": round(a["toi_uu"]),
        })
    by_sp.sort(key=lambda x: -x["toi_uu"])

    ck_tb_all = (T["tong_giam"] / T["tam_tinh"] * 100.0) if T["tam_tinh"] > 0 else 0.0

    # Tối ưu tách Mây / Gỗ / Tổng — thứ tự cố định để UI luôn hiển thị đủ ô.
    # "Ghế Papasan" + "Chưa phân loại" chỉ hiện khi THỰC SỰ có đơn (miễn CK, tối ưu=0).
    by_loai = []
    for key in ("Đồ Mây", "Đồ Gỗ", "Ghế Papasan", "Chưa phân loại"):
        a = T_loai.get(key)
        if not a:
            if key in ("Chưa phân loại", "Ghế Papasan"):
                continue  # chỉ hiện khi thực sự có đơn loại này
            a = {"loai_don": key, "so_don": 0, "tam_tinh": 0.0, "tong_giam": 0.0,
                 "toi_uu": 0.0, "toi_uu_hcns": 0.0,
                 "max_ck": max_ck_may if key == "Đồ Mây" else max_ck_go}
        ck_tb_l = (a["tong_giam"] / a["tam_tinh"] * 100.0) if a["tam_tinh"] > 0 else 0.0
        by_loai.append({
            "loai_don": a["loai_don"], "max_ck": a["max_ck"], "so_don": a["so_don"],
            "tam_tinh": round(a["tam_tinh"]), "tong_giam": round(a["tong_giam"]),
            "ck_tb_pct": round(ck_tb_l, 2),
            "toi_uu": round(a["toi_uu"]),
            "toi_uu_hcns": round(a["toi_uu_hcns"]),
        })

    return {
        "max_ck": max_ck_go,          # tương thích ngược (trần Đồ Gỗ = mức cũ)
        "max_ck_go": max_ck_go,
        "max_ck_may": max_ck_may,
        "totals": {
            "so_don": T["so_don"], "tam_tinh": round(T["tam_tinh"]),
            "sau_ck": round(T["tam_tinh"] - T["tong_giam"]),  # tổng tiền sau chiết khấu
            "tong_giam": round(T["tong_giam"]), "ck_tb_pct": round(ck_tb_all, 2),
            "toi_uu": round(T["toi_uu"]),
            "toi_uu_hcns": round(sum(x["toi_uu_hcns"] for x in by_loai)),
        },
        "by_loai": by_loai,
        "by_sp": by_sp,
        "data": orders,
    }


@router.get("/orders-kd-list")
def orders_kd_list(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Danh sách NV KD cho tab Tối Ưu — theo tài khoản tạo đơn (mã NV ở prefix
    mã báo giá) map sang ho_ten HCNS. Không lệ thuộc text salesperson gõ tay."""
    rows = _safe_rows_silent(db, """
        SELECT COALESCE(e.ho_ten,
                        substring(q.quote_number from '^(NV[0-9]+)'),
                        '(không rõ)') AS name,
               COUNT(*) AS so_don
        FROM baogia.quotes q
        LEFT JOIN hcns.employees e
               ON LOWER(e.ma_nv) = LOWER(substring(q.quote_number from '^(NV[0-9]+)'))
        WHERE q.duyet_status = 'approved'
        GROUP BY 1
        ORDER BY 1
    """)
    return {"data": rows}


@router.get("/order-detail/{ma_bg}")
def order_detail(
    ma_bg: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Chi tiết 1 đơn báo giá để KT đối chiếu — gộp 5 phần:
        1. quote header + items (baogia)
        2. PO list + line items (muahang.purchase_orders + po_items)
        3. so_quy entries (thu/chi gắn ref_id=quote_number)
        4. cong_no entries (gắn ma_don=quote_number)
        5. vận chuyển (saleadmin.vanchuyen)

    Read-only cross-schema.
    """
    quote_rows = _safe_rows_silent(
        db,
        """
        SELECT q.id, q.quote_number AS ma_bg, q.customer_id, q.customer_name,
               q.customer_phone, q.customer_address, q.salesperson,
               q.created_at, q.duyet_status, q.duyet_luc, q.duyet_boi,
               q.tong_don, q.deposit, q.tien_thue, q.discount_amount,
               q.tien_trinh_mh, q.notes, q.ngay_giao_du_kien
        FROM baogia.quotes q
        WHERE q.quote_number = :ma_bg
        LIMIT 1
        """,
        ma_bg=ma_bg,
    )
    if not quote_rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Báo giá {ma_bg} không tồn tại")
    quote = quote_rows[0]

    items = _safe_rows_silent(
        db,
        """
        SELECT stt, product_name AS ten_sp, ma_don, dvt, so_luong,
               kich_thuoc_text AS kich_thuoc,
               mau_sac AS mau_go, mau_vai, mau_da, loai_son, addons,
               don_gia_tinh AS don_gia, thanh_tien, tien_do, ghi_chu
        FROM baogia.quote_items
        WHERE quote_id = :qid
        ORDER BY stt
        """,
        qid=quote["id"],
    )

    pos = _safe_rows_silent(
        db,
        """
        SELECT po.id AS po_id, po.ten_don, po.status, po.created_at,
               po.selected_ncc_id, po.discount, po.ngay_dat_xuong,
               s.name AS ncc_name
        FROM muahang.purchase_orders po
        LEFT JOIN muahang.suppliers s ON s.id = po.selected_ncc_id
        WHERE po.ref_bao_gia = :ma_bg
        ORDER BY po.created_at DESC
        """,
        ma_bg=ma_bg,
    )

    so_quy = _safe_rows_silent(
        db,
        """
        SELECT id, ngay, loai, so_tien, tai_khoan, noi_dung, lien_quan,
               phan_loai_cf, created_by, created_at
        FROM ketoan.so_quy
        WHERE ref_id = :ma_bg
        ORDER BY ngay DESC, id DESC
        """,
        ma_bg=ma_bg,
    )

    cong_no = _safe_rows_silent(
        db,
        """
        SELECT id, ngay, loai, doi_tac, so_tien, da_tra, con_lai,
               trang_thai, han_tra, ghi_chu
        FROM ketoan.cong_no
        WHERE ma_don = :ma_bg
        ORDER BY ngay DESC, id DESC
        """,
        ma_bg=ma_bg,
    )

    vc = _safe_rows_silent(
        db,
        """
        SELECT ma_vh, trang_thai, ngay_giao, don_vi_vc,
               chi_phi_vc, da_tra_dvvc, tien_thu_ho, dvvc_da_thu, ghi_chu
        FROM saleadmin.vanchuyen
        WHERE ma_don = :ma_bg
        LIMIT 1
        """,
        ma_bg=ma_bg,
    )

    # Thread trao đổi cross-app (KD/MKT/MH/CSKH/VC cùng post vào
    # marketing.lead_comments với prefix `[BG <quote_number>] …`).
    prefix = f"[BG {ma_bg}]"
    comment_rows = _safe_rows_silent(
        db,
        """
        SELECT lc.id, lc.thoi_gian, lc.nguoi_gui, lc.phong_ban,
               lc.vai_tro, lc.noi_dung, lc.hinh_anh
        FROM marketing.lead_comments lc
        JOIN baogia.customers c ON c.lead_id = lc.lead_id
        JOIN baogia.quotes     q ON q.customer_id = c.id
        WHERE q.quote_number = :ma_bg
          AND lc.noi_dung ILIKE :pat
        ORDER BY lc.thoi_gian ASC, lc.id ASC
        """,
        ma_bg=ma_bg,
        pat=prefix + "%",
    )

    # Resolve username → ho_ten 1 lượt
    usernames = {r["nguoi_gui"] for r in comment_rows if r.get("nguoi_gui")}
    nv_map: dict[str, str] = {}
    if usernames:
        try:
            rows = db.execute(
                text(
                    "SELECT username, ho_ten FROM hcns.employees "
                    "WHERE username = ANY(:names)"
                ),
                {"names": list(usernames)},
            ).all()
            nv_map = {r[0]: (r[1] or r[0]) for r in rows}
        except (ProgrammingError, OperationalError):
            db.rollback()

    comments: list[dict[str, Any]] = []
    for c in comment_rows:
        nd = c.get("noi_dung") or ""
        if nd.startswith(prefix):
            nd = nd[len(prefix):].lstrip()
        username = c.get("nguoi_gui") or ""
        comments.append({
            "id": c.get("id"),
            "thoi_gian": c["thoi_gian"].isoformat() if c.get("thoi_gian") else None,
            "nguoi_gui": username,
            "nguoi_gui_name": nv_map.get(username, username),
            "phong_ban": c.get("phong_ban") or "",
            "vai_tro": c.get("vai_tro") or "",
            "noi_dung": nd,
            "hinh_anh": c.get("hinh_anh"),
        })

    return {
        "quote": quote,
        "items": items,
        "pos": pos,
        "so_quy": so_quy,
        "cong_no": cong_no,
        "vanchuyen": vc[0] if vc else None,
        "comments": comments,
    }


# Alias backward-compat (UI cũ + workflow đối chiếu)
@router.get("/orders-pending-completion")
def list_orders_pending_completion(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Alias filter=pending."""
    return orders_overview(db, user, filter="pending")


# ============================================================================
# SP Master + Inventory: JOIN shared.products với ketoan.inventory_balance
# theo ma_sp loose. Cho phép kế toán xem tồn + đặt lại giá bán.
# ============================================================================

@router.get("/products-with-inventory")
def list_products_with_inventory(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    q: Optional[str] = Query(None),
    nhom_hang: Optional[str] = Query(None),
    active_only: bool = Query(True),
    only_in_stock: bool = Query(False, description="Chỉ SP có tồn > 0"),
):
    """SP master (shared.products) + tồn kho hiện tại (ketoan.inventory_balance).

    JOIN qua `ma_sp` loose. SP nào chưa có trong inventory_balance → so_luong_ton=0.
    """
    where = ["1=1"]
    params: dict[str, Any] = {}
    if active_only:
        where.append("p.active = TRUE")
    if q:
        where.append("(p.ma_sp ILIKE :kw OR p.ten_sp ILIKE :kw OR p.label ILIKE :kw)")
        params["kw"] = f"%{q.strip()}%"
    if nhom_hang:
        where.append("p.nhom_hang = :nh")
        params["nh"] = nhom_hang
    if only_in_stock:
        where.append("COALESCE(ib.so_luong_ton, 0) > 0")

    sql = f"""
        SELECT
            p.id, p.ma_sp, p.ten_sp, p.label, p.dvt, p.unit, p.nhom_hang,
            p.gia_co_ban, p.gia_von, p.hinh_anh, p.active, p.kich_thuoc_chuan, p.mau_chuan,
            COALESCE(ib.so_luong_ton, 0) AS so_luong_ton,
            COALESCE(ib.gia_von_bq, 0) AS gia_von_bq,
            COALESCE(ib.gia_tri_ton, 0) AS gia_tri_ton,
            ib.last_updated AS ton_last_updated,
            kp.id AS ketoan_product_id
        FROM shared.products p
        LEFT JOIN ketoan.product kp ON kp.ma_sp = p.ma_sp
        LEFT JOIN ketoan.inventory_balance ib ON ib.product_id = kp.id
        WHERE {' AND '.join(where)}
        ORDER BY p.thu_tu, p.ten_sp
        LIMIT 500
    """
    return {"data": _safe_rows(db, sql, **params)}


# ============================================================================
# TỒN KHO từ MUA HÀNG — đọc trực tiếp muahang.ton_kho_items + sửa giá nhập
# ============================================================================

@router.get("/ton-kho-mh")
def list_ton_kho_from_muahang(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    q: Optional[str] = Query(None),
    danh_muc: Optional[str] = Query(None),
    ncc: Optional[str] = Query(None),
    only_remaining: bool = Query(False, description="Chỉ dòng so_luong > 0"),
):
    """Đọc tồn kho từ phòng Mua Hàng (`muahang.ton_kho_items`) — mỗi dòng = 1 lô nhập."""
    where = ["1=1"]
    params: dict[str, Any] = {}
    if q:
        where.append("(t.ma_sp ILIKE :kw OR t.ten_sp ILIKE :kw)")
        params["kw"] = f"%{q.strip()}%"
    if danh_muc:
        where.append("t.danh_muc = :dm")
        params["dm"] = danh_muc
    if ncc:
        where.append("t.ncc_name ILIKE :ncc")
        params["ncc"] = f"%{ncc.strip()}%"
    if only_remaining:
        where.append("t.so_luong > 0")

    sql = f"""
        SELECT t.id, t.ma_sp, t.ten_sp, t.danh_muc, t.phan_khuc, t.kich_thuoc,
               t.vat_lieu, t.mau_sac, t.loai_son, t.phong_cach,
               t.ncc_name, t.ncc_id, t.ngay_nhap,
               t.so_luong, t.don_gia AS gia_nhap, t.thanh_tien,
               t.hinh_anh, t.ghi_chu, t.nguoi_nhap, t.created_at,
               sp.id AS product_master_id,
               COALESCE(sp.gia_co_ban, 0) AS gia_ban_hien_tai
        FROM muahang.ton_kho_items t
        LEFT JOIN shared.products sp ON sp.ma_sp = t.ma_sp
        WHERE {' AND '.join(where)}
        ORDER BY t.ngay_nhap DESC NULLS LAST, t.id DESC
        LIMIT 500
    """
    return {"data": _safe_rows(db, sql, **params)}


# NOTE: KHÔNG có endpoint PATCH giá nhập — giá nhập là việc của Mua Hàng,
# kế toán không can thiệp. Kế toán chỉ quyết định GIÁ BÁN qua
# `PATCH /api/external/products/{product_id}/gia-ban`.


@router.patch("/products/{product_id}/gia-ban")
def update_product_gia_ban(
    product_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    gia_ban: float = Query(..., gt=0, description="Giá bán mới"),
    note: Optional[str] = Query(None),
):
    """Kế toán đặt lại giá bán SP master. Update `shared.products.gia_co_ban`.

    Audit log: ai đổi, từ giá nào sang giá nào.
    """
    row = db.execute(
        text("SELECT id, ma_sp, ten_sp, gia_co_ban FROM shared.products WHERE id = :pid"),
        {"pid": product_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"SP id={product_id} không tồn tại")

    old_gia = float(row["gia_co_ban"] or 0)
    db.execute(
        text("UPDATE shared.products SET gia_co_ban = :g, updated_at = NOW() WHERE id = :pid"),
        {"g": gia_ban, "pid": product_id},
    )
    log_action(
        db, app="ketoan", action="update_gia_ban_sp", user=user,
        payload={
            "product_id": product_id, "ma_sp": row["ma_sp"], "ten_sp": row["ten_sp"],
            "old_gia": old_gia, "new_gia": gia_ban, "note": note,
        },
    )
    db.commit()
    return {"ok": True, "id": product_id, "old_gia": old_gia, "new_gia": gia_ban}


@router.patch("/ton-kho-mh/{ma_sp}/gia-ban")
def update_gia_ban_by_ma_sp(
    ma_sp: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    gia_ban: float = Query(..., gt=0, description="Giá bán mới"),
    note: Optional[str] = Query(None),
):
    """KT đặt giá bán theo ma_sp — auto-tạo `shared.products` nếu chưa có.

    Lấy ten_sp/danh_muc/dvt/hinh_anh từ dòng `muahang.ton_kho_items` mới nhất.
    """
    sp = db.execute(
        text("SELECT id, ma_sp, ten_sp, gia_co_ban FROM shared.products WHERE ma_sp = :ma LIMIT 1"),
        {"ma": ma_sp},
    ).mappings().first()

    if sp:
        old_gia = float(sp["gia_co_ban"] or 0)
        db.execute(
            text("UPDATE shared.products SET gia_co_ban = :g, updated_at = NOW() WHERE id = :pid"),
            {"g": gia_ban, "pid": sp["id"]},
        )
        product_id = sp["id"]
        created = False
        ten_sp = sp["ten_sp"]
    else:
        # Auto-create từ ton_kho_items mới nhất
        tk = db.execute(
            text("""
                SELECT ma_sp, ten_sp, danh_muc, kich_thuoc, vat_lieu, mau_sac, hinh_anh
                FROM muahang.ton_kho_items
                WHERE ma_sp = :ma
                ORDER BY ngay_nhap DESC NULLS LAST, id DESC LIMIT 1
            """),
            {"ma": ma_sp},
        ).mappings().first()
        if not tk:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"Không tìm thấy SP {ma_sp} trong tồn kho — kiểm tra lại mã.",
            )
        ten_sp = tk["ten_sp"] or ma_sp
        new_id = db.execute(
            text("""
                INSERT INTO shared.products
                    (ma_sp, ten_sp, nhom_hang, kich_thuoc_chuan, mau_chuan, hinh_anh, gia_co_ban, active)
                VALUES (:ma_sp, :ten_sp, :nhom, :kt, :mau, :img, :gia, TRUE)
                RETURNING id
            """),
            {
                "ma_sp": ma_sp,
                "ten_sp": ten_sp,
                "nhom": tk["danh_muc"],
                "kt": tk["kich_thuoc"],
                "mau": tk["mau_sac"],
                "img": tk["hinh_anh"],
                "gia": gia_ban,
            },
        ).scalar()
        product_id = new_id
        old_gia = 0.0
        created = True

    log_action(
        db, app="ketoan",
        action=("create_sp_and_set_gia" if created else "update_gia_ban_sp"),
        user=user,
        payload={
            "product_id": product_id, "ma_sp": ma_sp, "ten_sp": ten_sp,
            "old_gia": old_gia, "new_gia": gia_ban, "created": created, "note": note,
        },
    )
    db.commit()
    return {
        "ok": True, "id": product_id, "ma_sp": ma_sp,
        "old_gia": old_gia, "new_gia": gia_ban, "created": created,
    }


def _deduct_inventory_fifo(db: Session, ma_don: str) -> dict:
    """Trừ tồn kho FIFO trên `muahang.ton_kho_items` theo từng item trong đơn.

    Match SP loose: `quote_items.product_name` ↔ `ton_kho_items.ten_sp` (ILIKE).
    FIFO theo `ngay_nhap ASC` (lô cũ trừ trước).

    Returns:
        {
          "deducted": [...],        # detailed per-item lots
          "warnings": [...],        # missing inventory etc.
          "cost_summary": {          # Phase 4: dùng để sinh COGS movement + journal
              product_name: {
                  "total_qty": float,
                  "total_cost": float,        # SUM(lot.don_gia × take)
                  "weighted_avg_don_gia": float,
              }
          },
          "total_cogs": float,       # SUM(total_cost) — dùng cho journal Nợ 632 / Có 156
        }
    """
    if not ma_don:
        return {
            "deducted": [], "warnings": ["Không có ma_don"],
            "cost_summary": {}, "total_cogs": 0.0,
        }

    # 1. Lấy quote_id từ ma_don
    q = db.execute(
        text("SELECT id FROM baogia.quotes WHERE quote_number = :mn LIMIT 1"),
        {"mn": ma_don},
    ).first()
    if not q:
        return {
            "deducted": [], "warnings": [f"Không tìm thấy báo giá {ma_don}"],
            "cost_summary": {}, "total_cogs": 0.0,
        }
    quote_id = q[0]

    # 2. Lấy items của báo giá
    items = db.execute(
        text("""
            SELECT id, product_name, so_luong
            FROM baogia.quote_items
            WHERE quote_id = :qid AND product_name IS NOT NULL AND so_luong > 0
        """),
        {"qid": quote_id},
    ).mappings().all()
    if not items:
        return {
            "deducted": [], "warnings": [f"Báo giá {ma_don} không có item"],
            "cost_summary": {}, "total_cogs": 0.0,
        }

    deducted: list[dict] = []
    warnings: list[str] = []
    cost_summary: dict[str, dict] = {}  # product_name → {total_qty, total_cost}

    # 3. Cho mỗi item → trừ FIFO
    for it in items:
        product_name = (it["product_name"] or "").strip()
        qty_remain = int(it["so_luong"] or 0)
        if not product_name or qty_remain <= 0:
            continue

        # FIFO lô tồn của SP này
        lots = db.execute(
            text("""
                SELECT id, ma_sp, ten_sp, so_luong, don_gia, ngay_nhap
                FROM muahang.ton_kho_items
                WHERE ten_sp ILIKE :name AND so_luong > 0
                ORDER BY ngay_nhap ASC NULLS LAST, id ASC
            """),
            {"name": f"%{product_name}%"},
        ).mappings().all()

        if not lots:
            warnings.append(f"⚠️ Không tìm thấy tồn kho cho '{product_name}'")
            continue

        deducted_for_item = []
        item_total_qty = 0.0
        item_total_cost = 0.0
        for lot in lots:
            if qty_remain <= 0:
                break
            available = float(lot["so_luong"] or 0)
            take = min(available, qty_remain)
            don_gia = float(lot["don_gia"] or 0)
            cost_for_take = take * don_gia
            new_qty = available - take
            new_thanh_tien = new_qty * don_gia
            db.execute(
                text("""
                    UPDATE muahang.ton_kho_items
                    SET so_luong = :nq, thanh_tien = :tt, updated_at = NOW()
                    WHERE id = :i
                """),
                {"nq": new_qty, "tt": new_thanh_tien, "i": lot["id"]},
            )
            deducted_for_item.append({
                "lot_id": lot["id"],
                "ma_sp": lot["ma_sp"],
                "ten_sp": lot["ten_sp"],
                "deducted": take,
                "don_gia": don_gia,
                "cost": cost_for_take,
                "remaining": new_qty,
                "ngay_nhap": str(lot["ngay_nhap"]) if lot["ngay_nhap"] else None,
            })
            qty_remain -= take
            item_total_qty += take
            item_total_cost += cost_for_take

        if qty_remain > 0:
            warnings.append(
                f"⚠️ '{product_name}' thiếu {qty_remain} (đơn cần {it['so_luong']}, "
                f"đã trừ {it['so_luong'] - qty_remain})"
            )
        deducted.append({
            "product_name": product_name,
            "qty_ordered": int(it["so_luong"]),
            "qty_deducted": item_total_qty,
            "cost": item_total_cost,
            "lots": deducted_for_item,
        })

        # Cumulate cost_summary (1 SP có thể xuất hiện nhiều dòng quote_item)
        if product_name not in cost_summary:
            cost_summary[product_name] = {"total_qty": 0.0, "total_cost": 0.0}
        cost_summary[product_name]["total_qty"] += item_total_qty
        cost_summary[product_name]["total_cost"] += item_total_cost

    # Tính weighted_avg per product
    total_cogs = 0.0
    for name, agg in cost_summary.items():
        q = agg["total_qty"]
        c = agg["total_cost"]
        agg["weighted_avg_don_gia"] = (c / q) if q > 0 else 0.0
        total_cogs += c

    return {
        "deducted": deducted,
        "warnings": warnings,
        "cost_summary": cost_summary,
        "total_cogs": round(total_cogs, 2),
    }


@router.post("/vanchuyen/{ma_vh}/hoan-sla")
def toggle_hoan_sla(
    ma_vh: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    action: str = Query("hoan", description="hoan = chờ thu tiền (loại khỏi SLA2) / bo = bỏ hoãn"),
    ly_do: Optional[str] = Query(None),
):
    """KT đánh dấu đơn ĐÃ GIAO nhưng CHƯA THU TIỀN → tạm HOÃN: loại khỏi tính trễ
    SLA2 cho tới khi thu được tiền + đối chiếu (anh Quang 2026-08-18). Ghi mốc vào
    tien_trinh (stage 'hoan_sla' / 'bo_hoan_sla'). action='hoan' hoặc 'bo'."""
    import json as _json
    row = db.execute(
        text("SELECT trang_thai, ma_don FROM saleadmin.vanchuyen WHERE ma_vh = :mv"),
        {"mv": ma_vh},
    ).mappings().first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Không tìm thấy VC {ma_vh}")
    if row["trang_thai"] != "da_giao":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Chỉ hoãn được đơn đang 'Đã giao' (đơn này đang '{row['trang_thai']}')",
        )
    ma_don = row.get("ma_don") or ma_vh
    _ly_do = ly_do or ("Chờ thu tiền — hoãn SLA" if action == "hoan" else "Bỏ hoãn — tính SLA lại")
    stage = "hoan_sla" if action == "hoan" else "bo_hoan_sla"
    entry = {
        "stage": stage,
        "ts": datetime.now().isoformat(),
        "by": f"{user.username} (kế toán)",
        "note": _ly_do,
    }
    db.execute(
        text("UPDATE saleadmin.vanchuyen SET tien_trinh = COALESCE(tien_trinh,'[]'::jsonb) || CAST(:e AS jsonb), updated_at = NOW() WHERE ma_vh = :mv"),
        {"e": _json.dumps(entry), "mv": ma_vh},
    )
    # Bấm HOÃN → báo lên CEO/admin (anh Quang 2026-08-18): đơn đã giao nhưng KT
    # tạm hoãn (chưa thu tiền) → loại khỏi SLA, CEO cần nắm để tránh lạm dụng.
    if action == "hoan":
        try:
            from shared.services.notify import notify_many
            ceo_targets = [
                r[0] for r in db.execute(text(
                    "SELECT username FROM shared.users "
                    "WHERE role IN ('ceo','assistant_ceo','admin') AND active = true"
                )).all() if r[0]
            ]
            notify_many(
                db, ceo_targets,
                source_app="ketoan", event_type="kt_hoan_sla",
                title=f"KT hoãn đơn {ma_don} (chờ thu tiền)",
                message=f"Kế toán {user.username} hoãn đơn {ma_don} — {_ly_do}. "
                        f"Đơn đã giao nhưng chưa thu tiền → tạm loại khỏi SLA hoàn thành.",
                ref_type="vanchuyen", ref_id=ma_vh,
                url="https://ketoan.qlpps.com/",
                severity="warning", created_by=user.username,
            )
        except Exception:
            pass  # fail-soft — không để lỗi noti chặn việc hoãn
    db.commit()
    return {"ok": True, "ma_vh": ma_vh, "hoan": action == "hoan"}


@router.post("/vanchuyen/{ma_vh}/hoan-thanh")
def mark_vanchuyen_completed(
    ma_vh: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    note: Optional[str] = Query(None),
    tai_khoan: Optional[str] = Query(None, description="TK sổ quỹ cho tiền thu nốt (Tiền Mặt/ACB.../BIDV.../VPB); mặc định Tiền Mặt"),
):
    """Kế toán xác nhận đối chiếu thu/chi xong → chuyển VC sang `hoan_thanh`.

    Tác vụ (Phase 4 Revenue Recognition — 2026-04-28):
      1. Update vanchuyen.trang_thai = 'hoan_thanh' + push stage JSONB
      2. Sync baogia.quotes.tien_trinh_mh = 'Hoàn Thành'
      3. Trừ tồn kho FIFO trên muahang.ton_kho_items theo quote_items
      4. Sinh `ketoan.doanh_thu` (DT thuần = tong_chua_thue × (1 - discount/100))
      5. Sinh `ketoan.inventory_movement loai='xuat'` mỗi product (giá nhập FIFO)
      6. Sinh journal kép:
           - DT: Nợ 131 / Có 511, so_tien = dt_thuan
           - COGS: Nợ 632 / Có 156, so_tien = total_cogs (nếu > 0)
      7. Audit log
    """
    # Validate VC exists + status
    row = db.execute(
        text("SELECT id, trang_thai, ma_don, tien_trinh FROM saleadmin.vanchuyen WHERE ma_vh = :mv"),
        {"mv": ma_vh},
    ).mappings().first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Không tìm thấy VC {ma_vh}")
    if row["trang_thai"] != "da_giao":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"VC {ma_vh} đang ở trạng thái '{row['trang_thai']}', chỉ chuyển từ 'da_giao' sang 'hoan_thanh'"
        )

    today = date_cls.today()
    ma_don = row["ma_don"]

    # 1. Update VC trang_thai
    new_stage = {
        "stage": "hoan_thanh",
        "ts": datetime.now().isoformat(),
        "by": f"{user.username} (kế toán đối chiếu)",
        "note": note or "Kế toán đã đối chiếu thu/chi",
    }
    db.execute(
        text("""
            UPDATE saleadmin.vanchuyen
            SET trang_thai = 'hoan_thanh',
                tien_trinh = COALESCE(tien_trinh, '[]'::jsonb) || CAST(:stage AS jsonb),
                updated_at = NOW()
            WHERE ma_vh = :mv
        """),
        {"mv": ma_vh, "stage": json.dumps(new_stage)},
    )

    # 2. Sync baogia.quotes.tien_trinh_mh
    if ma_don:
        db.execute(
            text("""
                UPDATE baogia.quotes
                SET tien_trinh_mh = 'Hoàn Thành', updated_at = NOW()
                WHERE quote_number = :ma_don
            """),
            {"ma_don": ma_don},
        )

    # 3. Trừ tồn kho FIFO + thu thập cost_summary
    inv_result = _deduct_inventory_fifo(db, ma_don)
    total_cogs = float(inv_result.get("total_cogs", 0) or 0)
    cost_summary: dict = inv_result.get("cost_summary", {}) or {}

    # 4. Sinh ketoan.doanh_thu (1 dòng cho cả đơn)
    revenue_info: dict = {"created": False}
    journal_info: dict = {"created": False}
    movements_info: dict = {"created": 0, "skipped": 0}

    if ma_don:
        q = db.execute(text("""
            SELECT id, quote_number, customer_name, tong_chua_thue, tong_don,
                   discount_percent, tien_thue, salesperson
            FROM baogia.quotes WHERE quote_number = :mn
            LIMIT 1
        """), {"mn": ma_don}).mappings().first()

        if q:
            tong_cht = float(q["tong_chua_thue"] or 0)
            disc_pct = float(q["discount_percent"] or 0)
            dt_thuan = round(tong_cht * (1.0 - disc_pct / 100.0), 2) if tong_cht > 0 else 0.0

            # Trừ tiền CỌC đã ghi → phần CÒN LẠI mới ghi doanh thu + đẩy sổ quỹ lúc
            # hoàn thành (tránh double với cọc — anh Quang 2026-07-09).
            coc_da_ghi = float(db.execute(text("""
                SELECT COALESCE(SUM(so_tien), 0) FROM ketoan.doanh_thu
                WHERE ma_don = :mn AND loai_thanh_toan ILIKE '%cọc%'
            """), {"mn": ma_don}).scalar() or 0)
            con_lai = round(max(0.0, dt_thuan - coc_da_ghi), 2)

            # Loại doanh thu theo nhóm SP CHÍNH Mây/Gỗ (shared.products.nhom_master)
            _nm = db.execute(text("""
                SELECT DISTINCT p.nhom_master FROM baogia.quote_items qi
                JOIN shared.products p
                  ON lower(trim(p.label)) = lower(trim(qi.product_type))
                  OR lower(trim(p.ten_sp)) = lower(trim(qi.product_type))
                WHERE qi.quote_id = :qid AND p.nhom_master IN ('Đồ Gỗ', 'Đồ Mây')
            """), {"qid": q["id"]}).scalars().all()
            loai_dt = "Doanh thu đồ mây" if "Đồ Mây" in set(_nm) else "Doanh thu đồ gỗ lẻ"

            # TK sổ quỹ do KT CHỌN khi đối chiếu (tiền mặt / ngân hàng nào); mặc định Tiền Mặt
            _tk_sq = (tai_khoan or "").strip() or "Tiền Mặt"

            # 4a. Ghi doanh thu phần CÒN LẠI + đẩy SỔ QUỸ (idempotent qua
            # ma_don + loai_thanh_toan='Thanh Toán').
            if con_lai > 0:
                existed = db.execute(text("""
                    SELECT id FROM ketoan.doanh_thu
                    WHERE ma_don = :mn AND loai_thanh_toan = 'Thanh Toán' LIMIT 1
                """), {"mn": ma_don}).first()
                if not existed:
                    from ..models import DoanhThu as _DoanhThu
                    from ..services.so_quy_auto import sync_so_quy_from_doanh_thu as _sync_sq
                    from decimal import Decimal as _Dec
                    _dt = _DoanhThu(
                        ngay=today,
                        loai=loai_dt,
                        so_tien=_Dec(str(con_lai)),
                        nv_kinh_doanh=q["salesperson"],
                        ma_don=ma_don,
                        nguon="kd",
                        ngan_hang=_tk_sq,
                        loai_thanh_toan="Thanh Toán",
                        ghi_chu=(
                            f"Đơn hoàn thành {ma_don} — KH: {q['customer_name'] or '?'} "
                            f"— NV: {q['salesperson'] or '?'} (thu nốt sau cọc)"
                        ),
                        created_by=user.username,
                    )
                    db.add(_dt)
                    db.flush()
                    try:
                        _sync_sq(db, _dt)  # → ketoan.so_quy (thu), tai_khoan = _tk_sq
                    except Exception:
                        pass
                    revenue_info = {
                        "created": True, "id": _dt.id, "so_tien": con_lai,
                        "ma_don": ma_don, "loai": loai_dt,
                        "coc_da_tru": coc_da_ghi, "tai_khoan": _tk_sq,
                    }
                else:
                    revenue_info = {
                        "created": False, "skipped_existing_id": existed[0],
                        "ma_don": ma_don,
                    }

            # 5. Sinh inventory_movement loai='xuat' mỗi product
            if cost_summary:
                for product_name, agg in cost_summary.items():
                    qty = float(agg.get("total_qty", 0) or 0)
                    cost = float(agg.get("total_cost", 0) or 0)
                    avg_dg = float(agg.get("weighted_avg_don_gia", 0) or 0)
                    if qty <= 0:
                        continue
                    # Resolve ketoan.product.id qua ten_sp ILIKE
                    p_row = db.execute(text("""
                        SELECT id FROM ketoan.product
                        WHERE ten_sp ILIKE :n LIMIT 1
                    """), {"n": product_name}).first()
                    if not p_row:
                        # SP chưa có trong M1 inventory master — skip movement,
                        # chỉ log warning. KHÔNG fail.
                        movements_info["skipped"] += 1
                        inv_result.setdefault("warnings", []).append(
                            f"⚠️ COGS movement skipped: SP '{product_name}' "
                            f"chưa có trong ketoan.product"
                        )
                        continue
                    db.execute(text("""
                        INSERT INTO ketoan.inventory_movement
                          (ngay, product_id, loai, so_luong, don_gia, thanh_tien,
                           source_app, source_doc_id, ghi_chu, created_by)
                        VALUES
                          (:ngay, :pid, 'xuat', :sl, :dg, :tt,
                           'saleadmin', :sd, :gc, :by)
                    """), {
                        "ngay": today, "pid": p_row[0],
                        "sl": qty, "dg": avg_dg, "tt": cost,
                        "sd": f"{ma_vh}-COGS",
                        "gc": f"COGS đơn {ma_don} hoàn thành (FIFO from muahang.ton_kho_items)",
                        "by": user.username,
                    })
                    movements_info["created"] += 1

            # 6. Sinh journal kép — DT (Nợ 131 / Có 511) + COGS (Nợ 632 / Có 156)
            try:
                from ..services.journal import post_journal
                journal_lines = []
                rev_id = revenue_info.get("id")
                rev_id_int = int(rev_id) if isinstance(rev_id, int) else None
                if dt_thuan > 0 and revenue_info.get("created"):
                    # Bút toán DT
                    je_dt = post_journal(
                        db, ngay=today,
                        mo_ta=f"Ghi nhận DT đơn {ma_don} hoàn thành (VC {ma_vh})",
                        source_type="vc_hoan_thanh", source_id=ma_vh,
                        by_user=user.username,
                        lines=[
                            {"loai": "no", "account_code": "131",
                             "ref_table": "doanh_thu", "ref_id": rev_id_int,
                             "so_tien": dt_thuan,
                             "ghi_chu": f"Phải thu KH — {ma_don}"},
                            {"loai": "co", "account_code": "511",
                             "ref_table": "doanh_thu", "ref_id": rev_id_int,
                             "so_tien": dt_thuan,
                             "ghi_chu": f"DT bán hàng — {ma_don}"},
                        ],
                    )
                    journal_lines.append({"id": je_dt.id, "ma_but_toan": je_dt.ma_but_toan,
                                          "type": "DT"})
                if total_cogs > 0:
                    # ref_id phải INT — dùng quote_id thay vì ma_vh string
                    quote_id_row = db.execute(text(
                        "SELECT id FROM baogia.quotes WHERE quote_number = :mn LIMIT 1"
                    ), {"mn": ma_don}).first()
                    quote_int_id = int(quote_id_row[0]) if quote_id_row else None
                    je_cogs = post_journal(
                        db, ngay=today,
                        mo_ta=f"Ghi nhận GVHB đơn {ma_don} hoàn thành (VC {ma_vh})",
                        source_type="vc_hoan_thanh", source_id=ma_vh,
                        by_user=user.username,
                        lines=[
                            {"loai": "no", "account_code": "632",
                             "ref_table": "baogia.quotes", "ref_id": quote_int_id,
                             "so_tien": round(total_cogs, 2),
                             "ghi_chu": f"GVHB — {ma_don} (VC {ma_vh})"},
                            {"loai": "co", "account_code": "156",
                             "ref_table": "baogia.quotes", "ref_id": quote_int_id,
                             "so_tien": round(total_cogs, 2),
                             "ghi_chu": f"Xuất kho — {ma_don} (VC {ma_vh})"},
                        ],
                    )
                    journal_lines.append({"id": je_cogs.id, "ma_but_toan": je_cogs.ma_but_toan,
                                          "type": "COGS"})
                journal_info = {"created": len(journal_lines) > 0, "entries": journal_lines}
            except Exception as e:  # noqa: BLE001
                # Fail-soft: journal post lỗi không nên block hoàn thành VC.
                # Chỉ log + tiếp tục (DT/movement/inv vẫn được commit).
                journal_info = {"created": False, "error": str(e)[:200]}

    # 7. Phase 6A — Sync ads_phan_bo_don.vc_status + thang_hoan_thanh.
    # Ads tháng chi gắn với đơn này nay được flag "đã chảy về CP BH tháng X
    # hoàn thành" để PL calculator (Agent 6B) tổng hợp đúng matching.
    apb_synced = 0
    try:
        from ..services.ads_phan_bo import sync_vc_status_for_quote
        thang_ht = today.strftime("%Y-%m")
        if ma_don:
            apb_synced = sync_vc_status_for_quote(
                db, ma_don=ma_don,
                vc_status="hoan_thanh",
                thang_hoan_thanh=thang_ht,
            )
    except Exception as e:  # noqa: BLE001
        # Fail-soft: hook lỗi không block hoàn thành VC
        apb_synced = -1

    # 8. Invalidate PL cache
    try:
        from .bao_cao_pnl import invalidate_pl_cache
        invalidate_pl_cache()
    except Exception:
        pass

    log_action(
        db, app="ketoan", action="vc_hoan_thanh", user=user,
        payload={
            "ma_vh": ma_vh, "ma_don": ma_don, "note": note,
            "inventory_deducted": inv_result,
            "revenue": revenue_info,
            "movements": movements_info,
            "journal": journal_info,
            "ads_phan_bo_synced": apb_synced,
        },
    )
    db.commit()

    # ZNS: gửi "Giao Hàng Thành Công" sau khi KT xác nhận hoàn thành (fail-soft)
    if ma_don:
        try:
            from shared.integrations.zalo_oa.worker import send_zns_for_delivered
            import threading
            threading.Thread(
                target=send_zns_for_delivered,
                args=(ma_don,),
                kwargs={"triggered_by": user.username},
                daemon=True,
            ).start()
        except Exception:
            pass

    return {
        "ok": True,
        "ma_vh": ma_vh,
        "ma_don": ma_don,
        "trang_thai": "hoan_thanh",
        "synced_baogia": bool(ma_don),
        "inventory": inv_result,
        "revenue": revenue_info,
        "movements": movements_info,
        "journal": journal_info,
        "ads_phan_bo_synced": apb_synced,
    }


# ============================================================================
# DROPDOWN — danh sách NCC + KH cho modal "Thêm công nợ"
# ============================================================================

@router.get("/suppliers")
def list_suppliers_for_dropdown(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    q: Optional[str] = Query(None, description="Lọc theo tên NCC"),
):
    """List NCC từ `muahang.suppliers` cho dropdown chọn đối tác công nợ phải trả."""
    where = ["1=1"]
    params: dict[str, Any] = {}
    if q:
        where.append("(name ILIKE :kw OR short_code ILIKE :kw)")
        params["kw"] = f"%{q.strip()}%"
    sql = f"""
        SELECT id, name, short_code, phone
        FROM muahang.suppliers
        WHERE {' AND '.join(where)}
        ORDER BY name
        LIMIT 1000
    """
    return {"data": _safe_rows_silent(db, sql, **params)}


@router.post("/vanchuyen/{ma_vh}/ketoan-approve")
def ketoan_approve_vanchuyen(
    ma_vh: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Kế Toán duyệt cuối cho 1 đơn vận chuyển đã `hoan_thanh`.

    Workflow: saleadmin chuyển VH sang `hoan_thanh` → app ketoan thấy nút
    `✓ Duyệt KT` → KT ấn → ghi `ketoan_approved_at/by` → UI chuyển sang
    `Đã xong`.

    Idempotent — duyệt lại không update lại timestamp/by.
    """
    if user.role not in ("admin", "ceo", "assistant_ceo", "manager", "kt"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ Kế Toán/Manager được duyệt")

    row = db.execute(text(
        "SELECT id, ma_don, trang_thai, ketoan_approved_at FROM saleadmin.vanchuyen WHERE ma_vh = :m"
    ), {"m": ma_vh}).mappings().first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"VH {ma_vh} không tồn tại")
    if row["trang_thai"] != "hoan_thanh":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"VH chưa ở trạng thái 'Đã giao thành công' (hiện: {row['trang_thai']})",
        )
    if row["ketoan_approved_at"]:
        return {"ok": True, "already_approved": True}

    db.execute(text("""
        UPDATE saleadmin.vanchuyen
        SET ketoan_approved_at = NOW(),
            ketoan_approved_by = :u
        WHERE ma_vh = :m
    """), {"u": user.username, "m": ma_vh})
    db.commit()
    log_action(
        db, app="ketoan", action="ketoan_approve_vanchuyen", user=user,
        resource=f"vanchuyen:{ma_vh}", payload={"ma_vh": ma_vh},
    )

    # ZNS "Giao hàng thành công" — bắn 1 lần khi KT duyệt cuối (fail-soft, chạy nền).
    # Chỉ tới đây khi đơn vừa chuyển từ chưa-duyệt → đã-duyệt (idempotent ở trên),
    # nên không gửi trùng. Lookup SĐT khách qua baogia.quotes theo ma_don.
    ma_don = row["ma_don"]
    if ma_don:
        try:
            from shared.integrations.zalo_oa.worker import send_zns_for_delivered
            import threading
            threading.Thread(
                target=send_zns_for_delivered,
                args=(ma_don,),
                kwargs={"triggered_by": user.username},
                daemon=True,
            ).start()
        except Exception:
            pass

    return {"ok": True, "approved_by": user.username}


@router.get("/customers")
def list_customers_for_dropdown(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    q: Optional[str] = Query(None, description="Lọc theo tên KH"),
):
    """List KH từ `baogia.customers` cho dropdown chọn đối tác công nợ phải thu."""
    where = ["1=1"]
    params: dict[str, Any] = {}
    if q:
        where.append("(ho_ten ILIKE :kw OR sdt ILIKE :kw)")
        params["kw"] = f"%{q.strip()}%"
    sql = f"""
        SELECT id, ho_ten, sdt, dia_chi
        FROM baogia.customers
        WHERE {' AND '.join(where)}
        ORDER BY ho_ten
        LIMIT 1000
    """
    return {"data": _safe_rows_silent(db, sql, **params)}
