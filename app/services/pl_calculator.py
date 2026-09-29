"""P&L calculator — Phase 4 Revenue Recognition + Phân Bổ Định Phí (2026-04-28).

Sprint Phase 4 reshape: trả response **22 dòng đầy đủ** chuẩn báo cáo lãi lỗ
Papasan, tách rõ:
  - Doanh thu thuần = DT thực hiện - chiết khấu
  - COGS (giá vốn FIFO từ inventory_movement)
  - Tài chính (DT TC + CP TC: lãi vay + phí NH + khác)
  - CP bán hàng (biến phí: hoa hồng/lương OT KD-MKT/ads/VC/khuyến mãi/khác
                định phí: lương cơ bản KD-MKT/thuê showroom/khấu hao TSCĐ BH/...)
  - CP quản lý (biến phí: VPP/đào tạo/hội họp/quà...
               định phí: lương HCNS-KT-CEO/thuê VP/điện nước/internet/khấu hao TSCĐ QL)
  - Thu nhập khác / CP khác
  - LN trước thuế → Thuế TNDN 20% → LNST

Quy ước Papasan:
  - DT thuần dùng `quotes.tong_chua_thue` × (1 - discount/100), KHÔNG dùng `tong_don` (có VAT).
  - BHXH gộp vào lương (multiplier 1.235 cho phần BHXH cty đóng).
  - Phân bổ định phí: `chi_phi_co_dinh.so_thang_phan_bo` >1 → chia đều.
  - Khấu hao TSCĐ: query `khau_hao_log` JOIN `tai_san_co_dinh.bo_phan` ('ban_hang' | 'quan_ly').
"""
from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from ..models import (
    ChiPhiCoDinh, ChiPhiPhatSinh, CongNo, DoanhThu,
)


# Thuế TNDN
TAX_RATE_TNDN = 0.20

# Phòng ban → ban_hang (KD/MKT) — còn lại là ban quản lý (HCNS/KT/CEO/...)
BH_PB_KEYS = ("kinh doanh", "kd", "sale", "marketing", "mkt")

# BHXH multiplier — gộp BHXH cty đóng vào lương cơ bản (Papasan quy ước):
#   Tổng cty đóng ≈ 23.5% lương đóng BH (BHXH 17.5 + BHYT 3 + BHTN 1 + KPCĐ 2)
BHXH_CTY_MULTIPLIER = 1.235


# -------------------- single sums (legacy compat) --------------------

def sum_doanh_thu(
    db: Session,
    tu_ngay: date,
    den_ngay: date,
    loai: Optional[str] = None,
) -> tuple[Decimal, int]:
    """Trả về (tổng so_tien, số phiếu) trong khoảng ngày."""
    stmt = select(
        func.coalesce(func.sum(DoanhThu.so_tien), 0),
        func.count(DoanhThu.id),
    ).where(DoanhThu.ngay >= tu_ngay, DoanhThu.ngay <= den_ngay)
    if loai:
        stmt = stmt.where(DoanhThu.loai == loai)
    total, count = db.execute(stmt).one()
    return Decimal(total or 0), int(count or 0)


def sum_chi_phi_phat_sinh(
    db: Session,
    tu_ngay: date,
    den_ngay: date,
    loai: Optional[str] = None,
) -> tuple[Decimal, int]:
    stmt = select(
        func.coalesce(func.sum(ChiPhiPhatSinh.so_tien), 0),
        func.count(ChiPhiPhatSinh.id),
    ).where(ChiPhiPhatSinh.ngay >= tu_ngay, ChiPhiPhatSinh.ngay <= den_ngay)
    if loai:
        stmt = stmt.where(ChiPhiPhatSinh.loai_chi_phi == loai)
    total, count = db.execute(stmt).one()
    return Decimal(total or 0), int(count or 0)


def sum_chi_phi_co_dinh(
    db: Session,
    tu_ngay: date,
    den_ngay: date,
) -> tuple[Decimal, int]:
    """Tính tổng chi phí cố định ÁP DỤNG trong [tu_ngay, den_ngay] (legacy)."""
    rows = db.execute(
        select(
            ChiPhiCoDinh.id,
            ChiPhiCoDinh.thang_bat_dau,
            ChiPhiCoDinh.so_tien_thang,
            ChiPhiCoDinh.lap_lai,
        ).where(ChiPhiCoDinh.thang_bat_dau <= den_ngay)
    ).all()

    total = Decimal(0)
    count = 0
    for _id, thang_bat_dau, so_tien_thang, lap_lai in rows:
        st = Decimal(so_tien_thang or 0)
        if lap_lai:
            start_month = max(thang_bat_dau, tu_ngay.replace(day=1))
            if start_month > den_ngay:
                continue
            months = (
                (den_ngay.year - start_month.year) * 12
                + (den_ngay.month - start_month.month)
                + 1
            )
            if months > 0:
                total += st * months
                count += 1
        else:
            if tu_ngay <= thang_bat_dau <= den_ngay:
                total += st
                count += 1
    return total, count


def sum_cong_no_by_loai(
    db: Session,
    loai: str,
    tu_ngay: Optional[date] = None,
    den_ngay: Optional[date] = None,
    chua_tra_only: bool = True,
) -> tuple[Decimal, int]:
    """Tổng con_lai (hoặc so_tien nếu chua_tra_only=False) theo loại công nợ."""
    stmt = select(
        func.coalesce(func.sum(CongNo.con_lai if chua_tra_only else CongNo.so_tien), 0),
        func.count(CongNo.id),
    ).where(CongNo.loai == loai)
    if chua_tra_only:
        stmt = stmt.where(CongNo.trang_thai == "chua_tra")
    if tu_ngay:
        stmt = stmt.where(CongNo.ngay >= tu_ngay)
    if den_ngay:
        stmt = stmt.where(CongNo.ngay <= den_ngay)
    total, count = db.execute(stmt).one()
    return Decimal(total or 0), int(count or 0)


# -------------------- group by (legacy compat) --------------------

def group_by_date_doanh_thu(
    db: Session,
    tu_ngay: date,
    den_ngay: date,
    by: str = "ngay",
) -> list[tuple[str, Decimal, int]]:
    if by == "thang":
        key_col = func.to_char(DoanhThu.ngay, "YYYY-MM")
    else:
        key_col = func.to_char(DoanhThu.ngay, "YYYY-MM-DD")
    stmt = (
        select(
            key_col.label("k"),
            func.coalesce(func.sum(DoanhThu.so_tien), 0),
            func.count(DoanhThu.id),
        )
        .where(DoanhThu.ngay >= tu_ngay, DoanhThu.ngay <= den_ngay)
        .group_by("k")
        .order_by("k")
    )
    return [(k, Decimal(s or 0), int(c or 0)) for k, s, c in db.execute(stmt).all()]


def group_by_loai_chi_phi(
    db: Session,
    tu_ngay: date,
    den_ngay: date,
) -> list[tuple[str, Decimal, int]]:
    stmt = (
        select(
            func.coalesce(ChiPhiPhatSinh.loai_chi_phi, "Khác").label("k"),
            func.coalesce(func.sum(ChiPhiPhatSinh.so_tien), 0),
            func.count(ChiPhiPhatSinh.id),
        )
        .where(
            ChiPhiPhatSinh.ngay >= tu_ngay,
            ChiPhiPhatSinh.ngay <= den_ngay,
        )
        .group_by("k")
        .order_by(func.sum(ChiPhiPhatSinh.so_tien).desc())
    )
    return [(k, Decimal(s or 0), int(c or 0)) for k, s, c in db.execute(stmt).all()]


# ─── Phase 4 P&L — Helpers ───────────────────────────────────────────────────

def _parse_thang(thang: str) -> tuple[date, date]:
    """'YYYY-MM' → (first_day, last_day)."""
    y, m = thang.split("-")
    yy, mm = int(y), int(m)
    tu = date(yy, mm, 1)
    den = date(yy, mm, monthrange(yy, mm)[1])
    return tu, den


def _safe_scalar(db: Session, sql: str, **params) -> float:
    try:
        v = db.execute(text(sql), params).scalar()
        return float(v or 0)
    except (ProgrammingError, OperationalError):
        db.rollback()
        return 0.0


def _sum_doanh_thu_thuc_hien(db: Session, tu: date, den: date) -> float:
    """DT thực hiện = TỔNG GIÁ TRỊ ĐƠN HÀNG hoàn thành trong kỳ (chưa VAT).

    Anh Quang chốt 2026-06-20: doanh thu thuần phải lấy theo TỔNG TIỀN ĐƠN HÀNG
    (baogia.quotes.tong_chua_thue — đã trừ chiết khấu, chưa gồm VAT vì VAT không
    phải doanh thu), của các ĐƠN HOÀN THÀNH trong kỳ (vanchuyen='hoan_thanh') —
    KHỚP đúng tập đơn với COGS (matching principle).

    Trước đây lấy SUM(ketoan.doanh_thu.so_tien) = tiền THU thực (đặt cọc/trả góp)
    → lệch kỳ và không khớp giá vốn. Fallback về doanh_thu nếu chưa có đơn hoàn
    thành nào khớp (vd dữ liệu cũ).
    """
    sql_don = """
        SELECT COALESCE(SUM(q.tong_chua_thue), 0)
        FROM baogia.quotes q
        WHERE q.quote_number IN (
            SELECT DISTINCT ma_don FROM saleadmin.vanchuyen
            WHERE trang_thai = 'hoan_thanh'
              AND COALESCE(ketoan_approved_at::date, ngay_giao, updated_at::date) >= :tu
              AND COALESCE(ketoan_approved_at::date, ngay_giao, updated_at::date) <= :den
        )
    """
    dt_don = _safe_scalar(db, sql_don, tu=tu, den=den)
    if dt_don > 0:
        return dt_don
    sql = """
        SELECT COALESCE(SUM(so_tien), 0)
        FROM ketoan.doanh_thu
        WHERE ngay >= :tu AND ngay <= :den
          AND COALESCE(loai, '') NOT IN ('Hoàn Tiền', 'Hoan Tien')
    """
    return _safe_scalar(db, sql, tu=tu, den=den)


def _sum_cogs(db: Session, tu: date, den: date) -> float:
    """COGS = giá vốn NCC của ĐƠN HOÀN THÀNH trong kỳ (anh Quang chốt 2026-06-20).

    Khớp nguyên tắc phù hợp (matching): doanh thu ghi theo đơn hoàn thành →
    giá vốn cũng theo đơn hoàn thành. Giá vốn = SUM(ketoan.cong_no.so_tien,
    loai='phai_tra') của các đơn (ma_don) có vận chuyển HOÀN THÀNH trong kỳ
    (cùng định nghĩa với _count_orders_hoan_thanh).

    Nếu chưa có công nợ NCC → fallback inventory_movement (FIFO) nếu có.
    """
    ncc = _safe_scalar(db, """
        SELECT COALESCE(SUM(cn.so_tien), 0)
        FROM ketoan.cong_no cn
        WHERE cn.loai = 'phai_tra'
          AND cn.ma_don IN (
            SELECT DISTINCT ma_don FROM saleadmin.vanchuyen
            WHERE trang_thai = 'hoan_thanh'
              AND COALESCE(ketoan_approved_at::date, ngay_giao, updated_at::date) >= :tu
              AND COALESCE(ketoan_approved_at::date, ngay_giao, updated_at::date) <= :den
          )
    """, tu=tu, den=den)
    if ncc > 0:
        return ncc
    return _safe_scalar(db, """
        SELECT COALESCE(SUM(thanh_tien), 0)
        FROM ketoan.inventory_movement
        WHERE loai = 'xuat'
          AND ngay >= :tu AND ngay <= :den
    """, tu=tu, den=den)


def _sum_lai_vay(db: Session, tu: date, den: date) -> float:
    """SUM lãi vay đã trả trong kỳ (khoan_vay_giao_dich)."""
    return _safe_scalar(db, """
        SELECT COALESCE(SUM(
            CASE
                WHEN gd.loai = 'tra_lai' THEN gd.so_tien
                WHEN gd.loai = 'tra_goc_lai' THEN COALESCE(gd.so_tien_lai, 0)
                ELSE 0
            END
        ), 0)
        FROM ketoan.khoan_vay_giao_dich gd
        WHERE gd.ngay >= :tu AND gd.ngay <= :den
    """, tu=tu, den=den)


def _sum_cp_phat_sinh_filter(
    db: Session, tu: date, den: date,
    nhom: Optional[str] = None,
    name_like: Optional[str] = None,        # ILIKE pattern
    name_like_any: Optional[list[str]] = None,  # multi ILIKE OR
    exclude_name_like: Optional[list[str]] = None,
    also_ten_khoan: bool = False,           # khớp cả ten_khoan (mô tả), không chỉ loai_chi_phi
) -> float:
    """SUM chi_phi_phat_sinh.so_tien with flexible filters.

    `also_ten_khoan=True`: name_like_any/exclude_name_like khớp trên CẢ
    `loai_chi_phi` LẪN `ten_khoan` (nhiều khoản ghi từ khoá ở mô tả ten_khoan,
    vd 'Hoàn tiền khách', 'tạm ứng', 'chi phí quảng cáo').
    """
    where = ["ngay >= :tu", "ngay <= :den"]
    params: dict[str, Any] = {"tu": tu, "den": den}
    if nhom:
        where.append("nhom_chi_phi = :nhom")
        params["nhom"] = nhom
    if name_like:
        where.append("LOWER(COALESCE(loai_chi_phi, '')) LIKE :nl")
        params["nl"] = name_like.lower()
    if name_like_any:
        ors = []
        for i, p in enumerate(name_like_any):
            k = f"nla_{i}"
            if also_ten_khoan:
                ors.append(
                    f"(LOWER(COALESCE(loai_chi_phi, '')) LIKE :{k} "
                    f"OR LOWER(COALESCE(ten_khoan, '')) LIKE :{k})"
                )
            else:
                ors.append(f"LOWER(COALESCE(loai_chi_phi, '')) LIKE :{k}")
            params[k] = p.lower()
        if ors:
            where.append("(" + " OR ".join(ors) + ")")
    if exclude_name_like:
        ors = []
        for i, p in enumerate(exclude_name_like):
            k = f"exn_{i}"
            if also_ten_khoan:
                ors.append(
                    f"(LOWER(COALESCE(loai_chi_phi, '')) NOT LIKE :{k} "
                    f"AND LOWER(COALESCE(ten_khoan, '')) NOT LIKE :{k})"
                )
            else:
                ors.append(f"LOWER(COALESCE(loai_chi_phi, '')) NOT LIKE :{k}")
            params[k] = p.lower()
        if ors:
            where.append("(" + " AND ".join(ors) + ")")
    sql = f"""
        SELECT COALESCE(SUM(so_tien), 0)
        FROM ketoan.chi_phi_phat_sinh
        WHERE {' AND '.join(where)}
    """
    return _safe_scalar(db, sql, **params)


def _sum_co_dinh_phan_bo(
    db: Session, thang: str, nhom: str,
    name_like_any: Optional[list[str]] = None,
    exclude_name_like_any: Optional[list[str]] = None,
) -> float:
    """SUM định phí phân bổ vào tháng `thang` (YYYY-MM) thuộc nhom.

    Phase 5A — fix bug `lap_lai` bị bỏ qua khi tính các tháng sau start.
    Refactor sang single SQL aggregation, branch theo (lap_lai, so_thang_phan_bo):

      | lap_lai | so_thang_phan_bo | Hành vi tại tháng X                              |
      |---------|------------------|--------------------------------------------------|
      | TRUE    | 1                | Lặp mãi: `so_tien_thang` nếu X >= thang_bat_dau  |
      | TRUE    | N>1              | Phân bổ N tháng rồi DỪNG (chu kỳ N tháng)        |
      | FALSE   | 1                | 1 lần đúng tháng `thang_bat_dau`                 |
      | FALSE   | N>1              | Phân bổ đều N tháng từ start (trả 1 lần / N kỳ)  |

    `name_like_any` / `exclude_name_like_any` filter ILIKE trên
    loai_chi_phi/ten_khoan (lowercase substring patterns).
    """
    where = ["nhom_chi_phi = :nhom", "so_tien_thang > 0", "thang_bat_dau IS NOT NULL"]
    params: dict[str, Any] = {"nhom": nhom, "thang": thang}
    if name_like_any:
        ors = []
        for i, p in enumerate(name_like_any):
            k = f"nla_{i}"
            ors.append(
                f"(LOWER(COALESCE(loai_chi_phi, '')) LIKE :{k} "
                f"OR LOWER(COALESCE(ten_khoan, '')) LIKE :{k})"
            )
            params[k] = p.lower()
        if ors:
            where.append("(" + " OR ".join(ors) + ")")
    if exclude_name_like_any:
        ands = []
        for i, p in enumerate(exclude_name_like_any):
            k = f"exn_{i}"
            ands.append(
                f"(LOWER(COALESCE(loai_chi_phi, '')) NOT LIKE :{k} "
                f"AND LOWER(COALESCE(ten_khoan, '')) NOT LIKE :{k})"
            )
            params[k] = p.lower()
        if ands:
            where.append("(" + " AND ".join(ands) + ")")

    sql = f"""
        SELECT COALESCE(SUM(
          CASE
            -- Lặp mãi mỗi tháng từ start (lap_lai=TRUE, N=1)
            WHEN lap_lai = TRUE AND COALESCE(so_thang_phan_bo, 1) = 1 THEN
              CASE WHEN TO_CHAR(thang_bat_dau, 'YYYY-MM') <= :thang
                   THEN so_tien_thang::numeric ELSE 0 END
            -- Phân bổ đều N tháng (cả lap_lai=TRUE chu kỳ N>1 lẫn lap_lai=FALSE N>1)
            WHEN COALESCE(so_thang_phan_bo, 1) > 1 THEN
              CASE WHEN TO_CHAR(thang_bat_dau, 'YYYY-MM') <= :thang
                    AND TO_CHAR(
                          thang_bat_dau
                          + ((so_thang_phan_bo - 1) || ' months')::interval,
                          'YYYY-MM'
                        ) >= :thang
                   THEN so_tien_thang::numeric / so_thang_phan_bo
                   ELSE 0 END
            -- 1 lần đúng tháng start (lap_lai=FALSE, N=1)
            ELSE
              CASE WHEN TO_CHAR(thang_bat_dau, 'YYYY-MM') = :thang
                   THEN so_tien_thang::numeric ELSE 0 END
          END
        ), 0)
        FROM ketoan.chi_phi_co_dinh
        WHERE {' AND '.join(where)}
    """
    try:
        v = db.execute(text(sql), params).scalar()
        return float(v or 0)
    except (ProgrammingError, OperationalError):
        db.rollback()
        return 0.0


def _sum_co_dinh_prorated_by_day(
    db: Session, thang: str, nhom: str,
    name_like_any: Optional[list[str]] = None,
    exclude_name_like_any: Optional[list[str]] = None,
) -> float:
    """Phase 5B — SUM định phí prorated theo NGÀY cho tháng `thang` (YYYY-MM).

    Quy tắc:
        Cho mỗi row chi_phi_co_dinh có overlap với [m_start, m_end] (tháng X):
            so_tien_thang × (overlap_days / 30)
        - overlap_days = LEAST(COALESCE(ngay_ket_thuc, m_end), m_end)
                         - GREATEST(ngay_bat_dau, m_start) + 1
        - Convention: dùng 30 ngày làm mẫu số chuẩn (kế toán phổ biến).

    Vd: thuê VP từ 15/03/2026 → 14/03/2027, so_tien_thang=10M
        - Tháng 2026-03: 17/30 × 10M ≈ 5.67M  (15/3 → 31/3 = 17 ngày)
        - Tháng 2026-04: 30/30 × 10M = 10M
        - Tháng 2027-03: 14/30 × 10M ≈ 4.67M  (1/3 → 14/3 = 14 ngày)

    KHÔNG dùng `lap_lai` / `so_thang_phan_bo` — Phase 5B chỉ dùng cặp
    (ngay_bat_dau, ngay_ket_thuc). `ngay_ket_thuc IS NULL` = vô thời hạn.

    HÀM NÀY ĐỘC LẬP với `_sum_co_dinh_phan_bo` (Phase 4/5A) — dispatcher
    Phase 5C sẽ chọn dùng hàm nào dựa vào cột `phuong_phap_phan_bo`.

    `name_like_any` / `exclude_name_like_any`: filter ILIKE trên
    loai_chi_phi/ten_khoan (lowercase substring patterns).
    """
    where_extra = ""
    params: dict[str, Any] = {"nhom": nhom, "thang_first": f"{thang}-01"}

    if name_like_any:
        ors = []
        for i, p in enumerate(name_like_any):
            k = f"nla_{i}"
            ors.append(
                f"(LOWER(COALESCE(loai_chi_phi, '')) LIKE :{k} "
                f"OR LOWER(COALESCE(ten_khoan, '')) LIKE :{k})"
            )
            params[k] = p.lower()
        if ors:
            where_extra += " AND (" + " OR ".join(ors) + ")"
    if exclude_name_like_any:
        ands = []
        for i, p in enumerate(exclude_name_like_any):
            k = f"exn_{i}"
            ands.append(
                f"(LOWER(COALESCE(loai_chi_phi, '')) NOT LIKE :{k} "
                f"AND LOWER(COALESCE(ten_khoan, '')) NOT LIKE :{k})"
            )
            params[k] = p.lower()
        if ands:
            where_extra += " AND (" + " AND ".join(ands) + ")"

    sql = f"""
        WITH month_range AS (
            SELECT
                DATE_TRUNC('month', CAST(:thang_first AS DATE))::date AS m_start,
                (DATE_TRUNC('month', CAST(:thang_first AS DATE))
                    + INTERVAL '1 month' - INTERVAL '1 day')::date AS m_end
        )
        SELECT COALESCE(SUM(
            so_tien_thang::numeric * (
                GREATEST(
                    0,
                    (LEAST(COALESCE(cpcd.ngay_ket_thuc, mr.m_end), mr.m_end)
                     - GREATEST(cpcd.ngay_bat_dau, mr.m_start) + 1)
                )::numeric / 30
            )
        ), 0)
        FROM ketoan.chi_phi_co_dinh cpcd, month_range mr
        WHERE cpcd.nhom_chi_phi = :nhom
          AND cpcd.so_tien_thang > 0
          AND cpcd.ngay_bat_dau IS NOT NULL
          AND cpcd.ngay_bat_dau <= mr.m_end
          AND (cpcd.ngay_ket_thuc IS NULL OR cpcd.ngay_ket_thuc >= mr.m_start)
          {where_extra}
    """
    try:
        v = db.execute(text(sql), params).scalar()
        return float(v or 0)
    except (ProgrammingError, OperationalError):
        db.rollback()
        return 0.0


# ─── Phase 5C P&L — Method dispatcher + 4 method-specific helpers ────────────
#
# Phase 5C thêm 4 method mới ngoài 'duong_thang' (5A) và 'prorated_by_day' (5B):
#   - front_loaded   : 50% tháng đầu, 50% chia đều (so_thang_phan_bo - 1) tháng còn lại
#   - seasonal       : trọng số mùa Tết (T11/T12/T01/T02 = 60%; T3..T10 = 40%/8)
#                      có thể override qua phan_bo_manual JSONB
#   - by_revenue_pct : so_tien_thang là % doanh thu thực hiện trong tháng
#   - manual         : đọc phan_bo_manual JSONB lấy % của tháng × so_tien_thang
#
# Dispatcher KHÔNG re-implement logic 5A/5B — chỉ filter rows theo method
# rồi gọi helper tương ứng (late import / direct call cùng module).

# Trọng số seasonal mặc định (Tết Papasan):
_SEASONAL_DEFAULT = {
    "01": 0.20,  # Cao điểm Tết
    "02": 0.20,
    "11": 0.10,  # Cận Tết bắt đầu
    "12": 0.10,
    "03": 0.05,  # Thấp điểm sau Tết
    "04": 0.05,
    "05": 0.05,
    "06": 0.05,
    "07": 0.05,
    "08": 0.05,
    "09": 0.05,
    "10": 0.05,
}
# Tổng = 0.20*2 + 0.10*2 + 0.05*8 = 0.40 + 0.20 + 0.40 = 1.00 (60% Tết + 40% các tháng)


def _query_co_dinh_rows_by_method(
    db: Session, nhom: str, method: str,
) -> list[dict]:
    """Helper internal — lấy raw rows chi_phi_co_dinh theo nhom + method.

    Trả list dict (không object) để 4 helper Phase 5C dễ dùng.
    """
    sql = """
        SELECT id, thang_bat_dau, ngay_bat_dau, ngay_ket_thuc, so_tien_thang,
               so_thang_phan_bo, lap_lai, COALESCE(loai_chi_phi, '') AS loai_chi_phi,
               COALESCE(ten_khoan, '') AS ten_khoan,
               phuong_phap_phan_bo, phan_bo_manual
        FROM ketoan.chi_phi_co_dinh
        WHERE nhom_chi_phi = :nhom
          AND COALESCE(phuong_phap_phan_bo, 'duong_thang') = :method
          AND COALESCE(so_tien_thang, 0) > 0
    """
    try:
        rows = db.execute(text(sql), {"nhom": nhom, "method": method}).mappings().all()
    except (ProgrammingError, OperationalError):
        db.rollback()
        return []
    return [dict(r) for r in rows]


def _sum_co_dinh_front_loaded(
    db: Session, thang: str, nhom: str,
) -> float:
    """Phase 5C — front_loaded: 50% tháng đầu, 50% chia đều (N-1) tháng còn lại.

    Vd: chiến dịch ra mắt SP, so_tien_thang=100M, so_thang_phan_bo=4
        - Tháng 0: 50M
        - Tháng 1-3: (50M / 3) ≈ 16.67M mỗi tháng

    Nếu so_thang_phan_bo=1 → toàn bộ vào tháng đầu (giống front 100%).
    """
    rows = _query_co_dinh_rows_by_method(db, nhom, "front_loaded")
    total = 0.0
    for r in rows:
        t_start = r.get("thang_bat_dau")
        st = float(r.get("so_tien_thang") or 0)
        n = int(r.get("so_thang_phan_bo") or 1)
        if not t_start or st <= 0:
            continue
        start_ym = t_start.strftime("%Y-%m")
        if n <= 1:
            # Tất cả vào tháng đầu
            if start_ym == thang:
                total += st
            continue
        # Tính tháng cuối phân bổ
        ystart, mstart = int(start_ym[:4]), int(start_ym[5:])
        mend = mstart + n - 1
        yend = ystart + (mend - 1) // 12
        mend = ((mend - 1) % 12) + 1
        end_ym = f"{yend:04d}-{mend:02d}"
        if not (start_ym <= thang <= end_ym):
            continue
        if thang == start_ym:
            # Tháng đầu = 50%
            total += st * 0.5
        else:
            # Các tháng còn lại chia đều 50% / (N-1)
            total += (st * 0.5) / (n - 1)
    return total


def _sum_co_dinh_seasonal(
    db: Session, thang: str, nhom: str,
) -> float:
    """Phase 5C — seasonal: trọng số mùa Tết.

    Mặc định (_SEASONAL_DEFAULT):
        - T11/T12/T01/T02 = 20%/20% (Tết) + 10%/10% (cận Tết) → tổng 60%
        - T3..T10 = 5% mỗi tháng → tổng 40%

    Nếu row có `phan_bo_manual` → dùng làm override trọng số (giả định
    giá trị là % và sẽ được normalize về fraction).

    Mỗi row: tháng-trong-năm `mm` của `thang` lấy weight × so_tien_thang × 12
    (vì so_tien_thang ở method seasonal được hiểu là "ngân sách năm / 12 trung bình",
    tổng năm = so_tien_thang × 12).
    """
    rows = _query_co_dinh_rows_by_method(db, nhom, "seasonal")
    if not rows:
        return 0.0
    mm = thang[5:7]  # 'YYYY-MM' → 'MM'
    total = 0.0
    for r in rows:
        t_start = r.get("thang_bat_dau")
        st = float(r.get("so_tien_thang") or 0)
        if not t_start or st <= 0:
            continue
        # Chỉ tính nếu thang_bat_dau ≤ thang (đã active)
        start_ym = t_start.strftime("%Y-%m")
        if start_ym > thang:
            continue
        # Override weights nếu có phan_bo_manual
        weights_pct = r.get("phan_bo_manual")
        if isinstance(weights_pct, dict) and weights_pct:
            # Normalize % → fraction
            weight = weights_pct.get(mm) or weights_pct.get(thang)
            if weight is None:
                continue
            try:
                w = float(weight) / 100.0
            except (TypeError, ValueError):
                continue
        else:
            w = _SEASONAL_DEFAULT.get(mm, 0.0)
        # so_tien_thang × 12 = ngân sách năm; w = fraction tháng
        total += st * 12.0 * w
    return total


def _sum_co_dinh_by_revenue(
    db: Session, thang: str, nhom: str,
) -> float:
    """Phase 5C — by_revenue_pct: so_tien_thang là % doanh thu trong tháng.

    Vd hoa hồng KD 5%: so_tien_thang=5 → tháng có DT=200M → 200M × 5% = 10M

    Lấy doanh thu thực hiện trong tháng (cùng nguồn _sum_doanh_thu_thuc_hien).
    """
    rows = _query_co_dinh_rows_by_method(db, nhom, "by_revenue_pct")
    if not rows:
        return 0.0

    tu, den = _parse_thang(thang)
    dt_thang = _sum_doanh_thu_thuc_hien(db, tu, den)
    if dt_thang <= 0:
        return 0.0

    total = 0.0
    for r in rows:
        t_start = r.get("thang_bat_dau")
        pct = float(r.get("so_tien_thang") or 0)  # % vd 5
        if not t_start or pct <= 0:
            continue
        start_ym = t_start.strftime("%Y-%m")
        if start_ym > thang:
            continue
        ngay_ket = r.get("ngay_ket_thuc")
        if ngay_ket and ngay_ket < tu:
            continue
        total += dt_thang * (pct / 100.0)
    return total


def _sum_co_dinh_manual(
    db: Session, thang: str, nhom: str,
) -> float:
    """Phase 5C — manual: đọc phan_bo_manual JSONB.

    Format JSONB hỗ trợ:
        - {"01": 50, "02": 30, "03": 20}        → key 'MM', áp với mọi năm
        - {"YYYY-MM": pct}                      → key cụ thể năm-tháng
        - hỗn hợp                               → ưu tiên 'YYYY-MM' trước

    Mỗi row: amount_thang = so_tien_thang × pct / 100 (không nhân 12 vì user
    đã định nghĩa rõ tỉ lệ tháng trong tổng).
    """
    rows = _query_co_dinh_rows_by_method(db, nhom, "manual")
    if not rows:
        return 0.0
    mm = thang[5:7]  # 'MM'
    total = 0.0
    for r in rows:
        t_start = r.get("thang_bat_dau")
        st = float(r.get("so_tien_thang") or 0)
        manual = r.get("phan_bo_manual")
        if not t_start or st <= 0 or not isinstance(manual, dict):
            continue
        start_ym = t_start.strftime("%Y-%m")
        if start_ym > thang:
            continue
        # Ưu tiên key YYYY-MM, fallback MM
        pct_raw = manual.get(thang)
        if pct_raw is None:
            pct_raw = manual.get(mm)
        if pct_raw is None:
            continue
        try:
            pct = float(pct_raw)
        except (TypeError, ValueError):
            continue
        if pct <= 0:
            continue
        total += st * pct / 100.0
    return total


def _sum_co_dinh_method_dispatcher(
    db: Session, thang: str, nhom: str,
    ten_filter: Optional[str] = None,
) -> dict:
    """Phase 5C — Dispatcher: gộp 6 method phân bổ thành 1 entry point.

    Args:
        db: SQLAlchemy session.
        thang: 'YYYY-MM'.
        nhom: 'ban_hang' | 'quan_ly' | 'tai_chinh' | 'khac'.
        ten_filter: optional ILIKE pattern (lowercase substring) trên loai_chi_phi/ten_khoan
                    — chỉ áp dụng cho 'duong_thang' và 'prorated_by_day' (helper 5A/5B
                    có sẵn name_like_any). 4 method còn lại: dispatcher gọi không filter
                    để giữ scope đơn giản (UI dispatcher chính: nguyên nhom).

    Returns:
        {
          "tong": float,                      # tổng cả 6 method
          "by_method": {                      # breakdown theo method
              "duong_thang": float,
              "prorated_by_day": float,
              "front_loaded": float,
              "seasonal": float,
              "by_revenue_pct": float,
              "manual": float,
          }
        }
    """
    # Late lookup helper 5A/5B — cùng module nên direct reference an toàn
    fn_5a = _sum_co_dinh_phan_bo
    fn_5b = _sum_co_dinh_prorated_by_day

    name_like_any = [ten_filter.lower()] if ten_filter else None

    by_method = {
        "duong_thang": round(fn_5a(
            db, thang, nhom,
            name_like_any=name_like_any,
        ), 2),
        "prorated_by_day": round(fn_5b(
            db, thang, nhom,
            name_like_any=name_like_any,
        ), 2),
        "front_loaded": round(_sum_co_dinh_front_loaded(db, thang, nhom), 2),
        "seasonal": round(_sum_co_dinh_seasonal(db, thang, nhom), 2),
        "by_revenue_pct": round(_sum_co_dinh_by_revenue(db, thang, nhom), 2),
        "manual": round(_sum_co_dinh_manual(db, thang, nhom), 2),
    }
    # Lưu ý: helper 5A `_sum_co_dinh_phan_bo` không filter theo
    # `phuong_phap_phan_bo` nên sẽ scan TẤT CẢ rows. Để tránh double-count
    # khi caller dùng dispatcher, ta TRỪ phần đã được tính bởi 4 method 5C
    # khỏi 'duong_thang'. Nhưng vì 5A scan tất cả method và treat như duong_thang,
    # ta cần filter 5A xuống chỉ method='duong_thang'. Cách an toàn:
    # tính 'duong_thang' bằng truy vấn riêng của Phase 5C, không gọi 5A.
    # → Vì task yêu cầu KHÔNG đụng 5A/5B nhưng vẫn an toàn:
    #   gọi 5A vẫn cho ra số tổng "phân bổ kiểu cũ" cho mọi rows,
    #   khi user chuyển sang method khác sẽ trừ ra ở caller.
    # Để dispatcher trả "đúng tổng" (mỗi row chỉ tính 1 method), ta chuyển
    # 'duong_thang' sang truy vấn rows có method='duong_thang' và áp logic
    # tương tự 5A inline (KHÔNG sửa hàm 5A gốc).
    by_method["duong_thang"] = round(
        _sum_co_dinh_duong_thang_method_only(db, thang, nhom, name_like_any), 2,
    )
    by_method["prorated_by_day"] = round(
        _sum_co_dinh_prorated_method_only(db, thang, nhom, name_like_any), 2,
    )

    tong = round(sum(by_method.values()), 2)
    return {"tong": tong, "by_method": by_method}


# Nhóm định phí mà calc_pl_for_month đưa vào P&L (cp_ban_hang + cp_quan_ly).
NHOM_DINH_PHI_PL: tuple[str, ...] = ("ban_hang", "quan_ly")


def dinh_phi_phan_bo_thang(db: Session, thang: str) -> dict[str, float]:
    """Định phí (chi_phi_co_dinh) phân bổ vào tháng `thang` — ĐÚNG phần calc_pl_for_month
    dùng (dispatcher 6 phương pháp, tôn trọng so_thang_phan_bo). Trả {nhom: số, "tong": số}.
    Dùng chung cho Tổng quan / pnl để khớp KQKD, thay cho sum_chi_phi_co_dinh (legacy —
    cộng nguyên so_tien_thang mỗi tháng, bỏ qua so_thang_phan_bo).
    """
    out = {
        nhom: round(_sum_co_dinh_method_dispatcher(db, thang, nhom)["tong"], 2)
        for nhom in NHOM_DINH_PHI_PL
    }
    out["tong"] = round(sum(out.values()), 2)
    return out


def dinh_phi_phan_bo_khoang(db: Session, tu: date, den: date) -> float:
    """Tổng định phí phân bổ của MỌI tháng chạm khoảng [tu, den] — mỗi tháng tính TRỌN
    tháng (cùng đơn vị với KQKD theo tháng; không chia theo ngày)."""
    tong = 0.0
    y, m = tu.year, tu.month
    while (y, m) <= (den.year, den.month):
        tong += dinh_phi_phan_bo_thang(db, f"{y:04d}-{m:02d}")["tong"]
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return round(tong, 2)


def _sum_co_dinh_duong_thang_method_only(
    db: Session, thang: str, nhom: str,
    name_like_any: Optional[list[str]] = None,
) -> float:
    """Phase 5C dispatcher helper — duong_thang chỉ rows có method='duong_thang'.

    Logic giống `_sum_co_dinh_phan_bo` (5A) nhưng filter thêm phuong_phap_phan_bo.
    KHÔNG sửa hàm 5A — chỉ duplicate logic tối thiểu cho dispatcher.
    """
    rows = _query_co_dinh_rows_by_method(db, nhom, "duong_thang")
    if not rows:
        return 0.0
    total = 0.0
    for r in rows:
        # Apply name filter
        if name_like_any:
            loai = (r.get("loai_chi_phi") or "").lower()
            ten = (r.get("ten_khoan") or "").lower()
            if not any(p.replace("%", "") in loai or p.replace("%", "") in ten
                       for p in name_like_any):
                continue
        t_start = r.get("thang_bat_dau")
        st = float(r.get("so_tien_thang") or 0)
        n_phan_bo = int(r.get("so_thang_phan_bo") or 1)
        lap_lai = bool(r.get("lap_lai"))
        if not t_start or st <= 0:
            continue
        start_ym = t_start.strftime("%Y-%m")
        if n_phan_bo > 1:
            ystart, mstart = int(start_ym[:4]), int(start_ym[5:])
            mend = mstart + n_phan_bo - 1
            yend = ystart + (mend - 1) // 12
            mend = ((mend - 1) % 12) + 1
            end_ym = f"{yend:04d}-{mend:02d}"
            if start_ym <= thang <= end_ym:
                total += st / n_phan_bo
        elif lap_lai:
            if start_ym <= thang:
                total += st
        else:
            if start_ym == thang:
                total += st
    return total


def _sum_co_dinh_prorated_method_only(
    db: Session, thang: str, nhom: str,
    name_like_any: Optional[list[str]] = None,
) -> float:
    """Phase 5C dispatcher helper — prorated_by_day chỉ rows method='prorated_by_day'."""
    where_extra = (
        " AND COALESCE(phuong_phap_phan_bo, 'duong_thang') = 'prorated_by_day'"
    )
    params: dict[str, Any] = {"nhom": nhom, "thang_first": f"{thang}-01"}

    if name_like_any:
        ors = []
        for i, p in enumerate(name_like_any):
            k = f"nla_{i}"
            ors.append(
                f"(LOWER(COALESCE(loai_chi_phi, '')) LIKE :{k} "
                f"OR LOWER(COALESCE(ten_khoan, '')) LIKE :{k})"
            )
            params[k] = p.lower() if p.startswith("%") else f"%{p.lower()}%"
        if ors:
            where_extra += " AND (" + " OR ".join(ors) + ")"

    sql = f"""
        WITH month_range AS (
            SELECT
                DATE_TRUNC('month', CAST(:thang_first AS DATE))::date AS m_start,
                (DATE_TRUNC('month', CAST(:thang_first AS DATE))
                    + INTERVAL '1 month' - INTERVAL '1 day')::date AS m_end
        )
        SELECT COALESCE(SUM(
            so_tien_thang::numeric * (
                GREATEST(
                    0,
                    (LEAST(COALESCE(cpcd.ngay_ket_thuc, mr.m_end), mr.m_end)
                     - GREATEST(cpcd.ngay_bat_dau, mr.m_start) + 1)
                )::numeric / 30
            )
        ), 0)
        FROM ketoan.chi_phi_co_dinh cpcd, month_range mr
        WHERE cpcd.nhom_chi_phi = :nhom
          AND cpcd.so_tien_thang > 0
          AND cpcd.ngay_bat_dau IS NOT NULL
          AND cpcd.ngay_bat_dau <= mr.m_end
          AND (cpcd.ngay_ket_thuc IS NULL OR cpcd.ngay_ket_thuc >= mr.m_start)
          {where_extra}
    """
    try:
        v = db.execute(text(sql), params).scalar()
        return float(v or 0)
    except (ProgrammingError, OperationalError):
        db.rollback()
        return 0.0


def _count_co_dinh_phan_bo(db: Session, thang: str) -> int:
    """COUNT chi_phi_co_dinh phân bổ đa kỳ active trong tháng `thang`."""
    sql = """
        SELECT COUNT(*) FROM ketoan.chi_phi_co_dinh
        WHERE so_thang_phan_bo > 1
          AND TO_CHAR(thang_bat_dau, 'YYYY-MM') <= :thang
          AND TO_CHAR(
              thang_bat_dau + ((so_thang_phan_bo || ' months')::interval) - INTERVAL '1 day',
              'YYYY-MM'
          ) >= :thang
    """
    try:
        v = db.execute(text(sql), {"thang": thang}).scalar()
        return int(v or 0)
    except (ProgrammingError, OperationalError):
        db.rollback()
        return 0


def _sum_payroll_split(db: Session, thang: str) -> dict[str, dict]:
    """SUM hcns.payroll split theo BH/QL phòng ban.

    Returns:
        {
          "bh": {"luong_co_ban": float, "hoa_hong": float, "luong_ot": float,
                 "thuc_linh": float},
          "ql": {"luong_co_ban": float, "hoa_hong": float, "luong_ot": float,
                 "thuc_linh": float},
        }
    Nếu schema chưa có hoa_hong/luong_ot/luong_co_ban → fallback bằng thuc_linh.
    """
    out = {
        "bh": {"luong_co_ban": 0.0, "hoa_hong": 0.0, "luong_ot": 0.0, "thuc_linh": 0.0},
        "ql": {"luong_co_ban": 0.0, "hoa_hong": 0.0, "luong_ot": 0.0, "thuc_linh": 0.0},
    }
    # Try full schema
    sql = """
        SELECT COALESCE(LOWER(e.phong_ban), 'khac') AS pb,
               COALESCE(SUM(p.luong_co_ban), 0) AS luong_cb,
               COALESCE(SUM(p.hoa_hong), 0)     AS hoa_hong,
               COALESCE(SUM(p.luong_ot), 0)     AS luong_ot,
               COALESCE(SUM(p.thuc_linh), 0)    AS thuc_linh
        FROM hcns.payroll p
        LEFT JOIN hcns.employees e ON e.id = p.employee_id
        WHERE p.thang = :thang
        GROUP BY pb
    """
    try:
        rows = db.execute(text(sql), {"thang": thang}).all()
    except (ProgrammingError, OperationalError):
        db.rollback()
        # Fallback simpler — chỉ thuc_linh
        try:
            sql2 = """
                SELECT COALESCE(LOWER(e.phong_ban), 'khac') AS pb,
                       COALESCE(SUM(p.thuc_linh), 0) AS thuc_linh
                FROM hcns.payroll p
                LEFT JOIN hcns.employees e ON e.id = p.employee_id
                WHERE p.thang = :thang
                GROUP BY pb
            """
            rows = db.execute(text(sql2), {"thang": thang}).all()
            for pb, tl in rows:
                key = "bh" if any(k in (pb or "") for k in BH_PB_KEYS) else "ql"
                out[key]["thuc_linh"] += float(tl or 0)
                # Approximate luong_co_ban ≈ thuc_linh khi chưa có schema chi tiết
                out[key]["luong_co_ban"] += float(tl or 0)
            return out
        except (ProgrammingError, OperationalError):
            db.rollback()
            return out

    for pb, lcb, hh, lot, tl in rows:
        key = "bh" if any(k in (pb or "") for k in BH_PB_KEYS) else "ql"
        out[key]["luong_co_ban"] += float(lcb or 0)
        out[key]["hoa_hong"] += float(hh or 0)
        out[key]["luong_ot"] += float(lot or 0)
        out[key]["thuc_linh"] += float(tl or 0)
    return out


def _sum_ads(db: Session, tu: date, den: date) -> float:
    """Phase 4 legacy — SUM marketing.ads_cost trong khoảng ngày (fallback)."""
    return _safe_scalar(db, """
        SELECT COALESCE(SUM(chi_phi), 0)
        FROM marketing.ads_cost
        WHERE ngay >= :tu AND ngay <= :den
    """, tu=tu, den=den)


# ─── Phase 6B — Ads phân bổ theo đơn hoàn thành ──────────────────────────────
#
# Logic:
#   - Ads tháng Y (tính vào CP BH tháng Y) =
#       (a) phân bổ từ các ĐƠN hoàn thành trong tháng Y (vc_status='hoan_thanh',
#           quote_number IS NOT NULL) — kéo về ads_pool tháng-chi gốc
#       (b) cộng thêm phần `no_match` (ads pool không match đơn nào trong nhóm)
#           phát sinh ngay trong tháng_chi_ads = tháng Y
#
# Bảng `ketoan.ads_phan_bo_don` do Phase 6A tạo. Khi bảng chưa tồn tại
# → fail-soft fallback về `_sum_ads` (legacy: SUM marketing.ads_cost).

def _ads_phan_bo_table_exists(db: Session) -> bool:
    """Kiểm tra bảng `ketoan.ads_phan_bo_don` đã tồn tại chưa."""
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


def _sum_ads_phan_bo_thang(db: Session, thang: str) -> Optional[float]:
    """Phase 6B — SUM ads phân bổ vào tháng `thang`.

    Quy tắc:
        ads tháng Y = SUM(so_tien_phan_bo) WHERE
            (thang_hoan_thanh = Y AND vc_status = 'hoan_thanh' AND quote_number IS NOT NULL)
            OR
            (thang_chi_ads = Y AND loai_phan_bo = 'no_match')

    Returns:
        float khi OK; `None` nếu bảng chưa tồn tại → caller fallback về _sum_ads legacy.
    """
    if not _ads_phan_bo_table_exists(db):
        return None
    sql = """
        SELECT COALESCE(SUM(so_tien_phan_bo), 0)
        FROM ketoan.ads_phan_bo_don
        WHERE (
            (thang_hoan_thanh = :thang AND vc_status = 'hoan_thanh' AND quote_number IS NOT NULL)
            OR
            (thang_chi_ads = :thang AND loai_phan_bo = 'no_match')
        )
    """
    try:
        v = db.execute(text(sql), {"thang": thang}).scalar()
        return float(v or 0)
    except (ProgrammingError, OperationalError):
        db.rollback()
        return None


def _sum_ads_phan_bo_by_nhom(db: Session, thang: str) -> Optional[dict[str, float]]:
    """Phase 6B — Breakdown ads phân bổ tháng theo `nhom_master`.

    Cùng logic SQL với `_sum_ads_phan_bo_thang` nhưng GROUP BY nhom_master.
    `no_match` rows (loai_phan_bo='no_match', không match đơn) gom thành key 'no_match'.

    Returns:
        dict {nhom: so_tien} khi OK; `None` nếu bảng chưa tồn tại.
        Vd: {"Đồ Gỗ": 50_000_000, "Đồ Mây": 20_000_000, "Dự Án": 10_000_000, "no_match": 5_000_000}
    """
    if not _ads_phan_bo_table_exists(db):
        return None
    sql = """
        SELECT
            CASE
                WHEN loai_phan_bo = 'no_match' THEN 'no_match'
                ELSE COALESCE(nhom_master, 'Khác')
            END AS nhom_key,
            COALESCE(SUM(so_tien_phan_bo), 0) AS so_tien
        FROM ketoan.ads_phan_bo_don
        WHERE (
            (thang_hoan_thanh = :thang AND vc_status = 'hoan_thanh' AND quote_number IS NOT NULL)
            OR
            (thang_chi_ads = :thang AND loai_phan_bo = 'no_match')
        )
        GROUP BY nhom_key
    """
    try:
        rows = db.execute(text(sql), {"thang": thang}).all()
        return {str(k): float(v or 0) for k, v in rows}
    except (ProgrammingError, OperationalError):
        db.rollback()
        return None


def _sum_van_chuyen(db: Session, tu: date, den: date) -> float:
    """SUM saleadmin.vanchuyen.chi_phi_vc — chỉ đơn `hoan_thanh`, `updated_at` trong kỳ."""
    return _safe_scalar(db, """
        SELECT COALESCE(SUM(chi_phi_vc), 0)
        FROM saleadmin.vanchuyen
        WHERE trang_thai = 'hoan_thanh'
          AND COALESCE(ketoan_approved_at::date, ngay_giao, updated_at::date) >= :tu
          AND COALESCE(ketoan_approved_at::date, ngay_giao, updated_at::date) <= :den
    """, tu=tu, den=den)


def _sum_khau_hao(db: Session, thang: str, bo_phan: str) -> float:
    """SUM khau_hao_log.so_tien thang JOIN tai_san_co_dinh.bo_phan."""
    return _safe_scalar(db, """
        SELECT COALESCE(SUM(kh.so_tien), 0)
        FROM ketoan.khau_hao_log kh
        JOIN ketoan.tai_san_co_dinh ts ON ts.id = kh.tscd_id
        WHERE kh.thang = :thang AND ts.bo_phan = :bp
    """, thang=thang, bp=bo_phan)


def _sum_cp_khac_journal(db: Session, tu: date, den: date, account_code: str) -> float:
    """SUM journal_line.so_tien WHERE account_code AND loai='no' (Nợ 711/811)."""
    sql = """
        SELECT COALESCE(SUM(jl.so_tien), 0)
        FROM ketoan.journal_line jl
        JOIN ketoan.journal_entry je ON je.id = jl.journal_id
        WHERE jl.account_code = :ac
          AND je.trang_thai = 'da_post'
          AND je.ngay >= :tu AND je.ngay <= :den
    """
    # 711 (Thu nhập khác): số dư bên CÓ → cộng so_tien khi loai='co'
    # 811 (Chi phí khác): số dư bên NỢ → cộng so_tien khi loai='no'
    if account_code == "711":
        sql = sql + " AND jl.loai = 'co'"
    elif account_code == "811":
        sql = sql + " AND jl.loai = 'no'"
    return _safe_scalar(db, sql, ac=account_code, tu=tu, den=den)


def _count_orders_hoan_thanh(db: Session, tu: date, den: date) -> int:
    sql = """
        SELECT COUNT(*) FROM saleadmin.vanchuyen
        WHERE trang_thai = 'hoan_thanh'
          AND COALESCE(ketoan_approved_at::date, ngay_giao, updated_at::date) >= :tu
          AND COALESCE(ketoan_approved_at::date, ngay_giao, updated_at::date) <= :den
    """
    try:
        v = db.execute(text(sql), {"tu": tu, "den": den}).scalar()
        return int(v or 0)
    except (ProgrammingError, OperationalError):
        db.rollback()
        return 0


def _count_khau_hao_log(db: Session, thang: str) -> int:
    return int(_safe_scalar(db, """
        SELECT COUNT(*) FROM ketoan.khau_hao_log WHERE thang = :thang
    """, thang=thang))


def _count_chi_phi_giao_dich(db: Session, tu: date, den: date, thang: str) -> int:
    n_ps = int(_safe_scalar(db, """
        SELECT COUNT(*) FROM ketoan.chi_phi_phat_sinh
        WHERE ngay >= :tu AND ngay <= :den
    """, tu=tu, den=den))
    # Định phí áp dụng cho tháng = lap_lai trước đó OR start in month OR phân bổ đa kỳ
    n_cd = int(_safe_scalar(db, """
        SELECT COUNT(*) FROM ketoan.chi_phi_co_dinh
        WHERE (
            (so_thang_phan_bo = 1 AND lap_lai = TRUE
             AND TO_CHAR(thang_bat_dau, 'YYYY-MM') <= :thang)
         OR (so_thang_phan_bo = 1 AND lap_lai = FALSE
             AND TO_CHAR(thang_bat_dau, 'YYYY-MM') = :thang)
         OR (so_thang_phan_bo > 1
             AND TO_CHAR(thang_bat_dau, 'YYYY-MM') <= :thang
             AND TO_CHAR(
                 thang_bat_dau + ((so_thang_phan_bo || ' months')::interval) - INTERVAL '1 day',
                 'YYYY-MM'
             ) >= :thang)
        )
    """, tu=tu, den=den, thang=thang))
    return n_ps + n_cd


# ─── Main entry: calc_pl_for_month ───────────────────────────────────────────

def calc_pl_for_month(db: Session, thang: str) -> dict[str, Any]:
    """Tính P&L 1 tháng — Phase 4 reshape (22-line breakdown).

    Args:
        thang: 'YYYY-MM'

    Returns:
        dict với schema 22 dòng đầy đủ (xem docstring module).
    """
    tu, den = _parse_thang(thang)

    # ── 1. Doanh thu ─────────────────────────────────────────────────────────
    dt_thuc_hien = _sum_doanh_thu_thuc_hien(db, tu, den)
    chiet_khau = 0.0  # Phase 4 placeholder — chiết khấu đã trừ ở thời điểm sinh DT
    # Giảm trừ doanh thu = HOÀN TIỀN khách (chi_phi_phat_sinh 'Hoàn tiền') — trả lại
    # tiền cho khách của đơn ĐÃ ghi nhận DT ⇒ GIẢM TRỪ DOANH THU, không phải "CP khác"
    # (anh Quang chốt 2026-08-27: dọn phân loại P&L).
    giam_tru_dt = round(_sum_cp_phat_sinh_filter(
        db, tu, den, name_like_any=["%hoàn tiền%", "%hoan tien%"],
        also_ten_khoan=True,
    ), 2)
    dt_thuan = round(dt_thuc_hien - chiet_khau - giam_tru_dt, 2)

    # ── 2. COGS ──────────────────────────────────────────────────────────────
    cogs = round(_sum_cogs(db, tu, den), 2)
    ln_gop = round(dt_thuan - cogs, 2)

    # ── 3. Tài chính ─────────────────────────────────────────────────────────
    dt_tai_chinh = 0.0  # placeholder
    lai_vay = round(_sum_lai_vay(db, tu, den), 2)
    cp_tc_total = round(_sum_cp_phat_sinh_filter(db, tu, den, nhom="tai_chinh"), 2)
    phi_nh = round(max(0.0, cp_tc_total - lai_vay), 2)
    cp_tai_chinh = {
        "lai_vay": lai_vay,
        "phi_nh": phi_nh,
        "khac": 0.0,
        "tong": round(lai_vay + phi_nh, 2),
    }

    # ── 4. Lương payroll split ────────────────────────────────────────────────
    payroll = _sum_payroll_split(db, thang)
    pr_bh = payroll["bh"]
    pr_ql = payroll["ql"]

    # Lương cơ bản gộp BHXH (BH = KD/MKT)
    luong_cb_bh_with_bhxh = round(pr_bh["luong_co_ban"] * BHXH_CTY_MULTIPLIER, 2)
    luong_cb_ql_with_bhxh = round(pr_ql["luong_co_ban"] * BHXH_CTY_MULTIPLIER, 2)

    # ── 5. CP bán hàng (BH) ───────────────────────────────────────────────────
    bh_hoa_hong = round(pr_bh["hoa_hong"], 2)
    bh_luong_ot = round(pr_bh["luong_ot"], 2)

    # Phase 6B: ads tháng Y = phân bổ từ đơn hoàn thành T Y + no_match T Y.
    # Fail-soft: bảng `ketoan.ads_phan_bo_don` chưa tồn tại → fallback legacy
    # SUM marketing.ads_cost trong khoảng ngày của tháng.
    _ads_pb_total = _sum_ads_phan_bo_thang(db, thang)
    _ads_pb_by_nhom_raw = _sum_ads_phan_bo_by_nhom(db, thang)
    # Nguồn ads dự phòng = chi_phi_phat_sinh 'Marketing'/'ads'/'quảng cáo' (MỌI nhóm)
    # — KT ghi tiền ads thủ công. Trước đây các dòng này bị LOẠI khỏi bh_khac (tránh
    # double) NHƯNG ads_phan_bo_don lại =0 (marketing.ads_cost rỗng) ⇒ ads BỊ MẤT
    # HẲN khỏi P&L. Anh Quang chốt 2026-08-27: nếu ads_phan_bo=0 thì lấy chi_phi này.
    _ads_from_chi_phi = round(_sum_cp_phat_sinh_filter(
        db, tu, den,
        name_like_any=["%marketing%", "%ads%", "%quảng cáo%", "%quang cao%"],
        also_ten_khoan=True,
    ), 2)
    if _ads_pb_total and _ads_pb_total > 0:
        bh_ads = round(_ads_pb_total, 2)
        bh_ads_source = "ketoan.ads_phan_bo_don"
        bh_ads_by_nhom = {
            k: round(float(v or 0), 2) for k, v in (_ads_pb_by_nhom_raw or {}).items()
        }
    elif _ads_from_chi_phi > 0:
        bh_ads = _ads_from_chi_phi
        bh_ads_source = "chi_phi_phat_sinh (Marketing/quảng cáo)"
        bh_ads_by_nhom: dict[str, float] = {}
    else:
        # Fallback legacy
        bh_ads = round(_sum_ads(db, tu, den), 2)
        bh_ads_source = "marketing.ads_cost (legacy)"
        bh_ads_by_nhom = {}

    bh_vc = round(_sum_van_chuyen(db, tu, den), 2)
    # Khuyến mãi = chi_phi_phat_sinh.nhom='ban_hang' ten chứa 'khuyen mai'
    bh_khuyen_mai = round(_sum_cp_phat_sinh_filter(
        db, tu, den, nhom="ban_hang",
        name_like_any=["%khuyến mãi%", "%khuyen mai%"],
    ), 2)
    # CP bán hàng phát sinh khác = nhom=ban_hang excluding khuyến mãi VÀ ads.
    # Ads bị loại (2026-06-20) vì đã tính riêng ở `bh_ads` (từ marketing.ads_cost
    # / ads_phan_bo_don) — nếu không loại, các dòng chi_phi_phat_sinh loai='Marketing'
    # nhom='ban_hang' sẽ làm ads bị ĐẾM 2 LẦN trong CP bán hàng.
    bh_cp_ps_khac = round(_sum_cp_phat_sinh_filter(
        db, tu, den, nhom="ban_hang",
        exclude_name_like=[
            "%khuyến mãi%", "%khuyen mai%",
            "%marketing%", "%ads%", "%quảng cáo%", "%quang cao%",
            # Hoàn tiền đã trừ ở giảm_trừ DT → KHÔNG để lọt vào chi phí BH (trừ 2 lần). L11
            "%hoàn tiền%", "%hoan tien%",
        ],
        also_ten_khoan=True,
    ), 2)
    # Note: VC đã có thể được counted vào nhom=ban_hang qua bridge cũ — để tránh
    # double count nếu cp_ps có ref_vc, ưu tiên loại bỏ. Đơn giản hoá: trừ nếu
    # cp_bh_khac > 0 và có entries có ref_vc trong nhom=ban_hang.
    try:
        cp_bh_with_refvc = float(db.execute(text("""
            SELECT COALESCE(SUM(so_tien), 0) FROM ketoan.chi_phi_phat_sinh
            WHERE ngay >= :tu AND ngay <= :den
              AND nhom_chi_phi = 'ban_hang'
              AND ref_vc IS NOT NULL
        """), {"tu": tu, "den": den}).scalar() or 0)
    except (ProgrammingError, OperationalError):
        db.rollback()
        cp_bh_with_refvc = 0.0
    bh_khac_clean = round(max(0.0, bh_cp_ps_khac - cp_bh_with_refvc), 2)

    bh_bien_phi_tong = round(
        bh_hoa_hong + bh_luong_ot + bh_ads + bh_vc + bh_khuyen_mai + bh_khac_clean, 2,
    )

    # Định phí BH — Phase 5C: dòng filter dùng method-only variant (chỉ rows
    # method='duong_thang' khớp keyword); dòng tổng dùng dispatcher (gộp 6 method).
    bh_thue_showroom = round(_sum_co_dinh_duong_thang_method_only(
        db, thang, "ban_hang",
        name_like_any=["%thuê%", "%thue%", "%showroom%"],
    ), 2)
    bh_khau_hao = round(_sum_khau_hao(db, thang, "ban_hang"), 2)
    # Phí thường xuyên BH = total all-method - thuê showroom (− khấu hao tính riêng)
    bh_co_dinh_total = round(_sum_co_dinh_method_dispatcher(db, thang, "ban_hang")["tong"], 2)
    bh_phi_tx = round(max(0.0, bh_co_dinh_total - bh_thue_showroom), 2)

    bh_dinh_phi_tong = round(
        luong_cb_bh_with_bhxh + bh_thue_showroom + bh_khau_hao + bh_phi_tx, 2,
    )

    cp_ban_hang = {
        "bien_phi": {
            "hoa_hong": bh_hoa_hong,
            "luong_ot": bh_luong_ot,
            "ads": bh_ads,
            # Phase 6B — breakdown ads phân bổ theo nhóm sản phẩm.
            # Trống `{}` khi bảng `ads_phan_bo_don` chưa tồn tại (legacy fallback).
            "ads_by_nhom": bh_ads_by_nhom,
            "ads_source": bh_ads_source,
            "van_chuyen": bh_vc,
            "khuyen_mai": bh_khuyen_mai,
            "khac": bh_khac_clean,
            "tong": bh_bien_phi_tong,
        },
        "dinh_phi": {
            "luong_co_ban_kd_mkt": luong_cb_bh_with_bhxh,
            "thue_showroom": bh_thue_showroom,
            "khau_hao_tscd_bh": bh_khau_hao,
            "phi_thuong_xuyen": bh_phi_tx,
            "tong": bh_dinh_phi_tong,
        },
        "tong": round(bh_bien_phi_tong + bh_dinh_phi_tong, 2),
    }

    # ── 6. CP quản lý (QL) ───────────────────────────────────────────────────
    ql_vpp = round(_sum_cp_phat_sinh_filter(
        db, tu, den, nhom="quan_ly",
        name_like_any=["%vpp%", "%văn phòng phẩm%", "%van phong pham%"],
    ), 2)
    ql_dao_tao = round(_sum_cp_phat_sinh_filter(
        db, tu, den, nhom="quan_ly",
        name_like_any=["%đào tạo%", "%dao tao%"],
    ), 2)
    ql_hoi_hop = round(_sum_cp_phat_sinh_filter(
        db, tu, den, nhom="quan_ly",
        name_like_any=["%hội họp%", "%hoi hop%", "%công tác%", "%cong tac%"],
    ), 2)
    ql_qua = round(_sum_cp_phat_sinh_filter(
        db, tu, den, nhom="quan_ly",
        # Bỏ '%qua%' trần (bắt nhầm "quản lý", "quảng cáo", "quá hạn"...) — chỉ giữ
        # pattern quà biếu rõ ràng. (Tier 3, 2026-08-28)
        name_like_any=["%quà%", "%quà biếu%", "%qua bieu%"],
    ), 2)
    # Biến phí QL — LOẠI TRỪ các khoản thanh toán NCC (anh Quang chốt 2026-06-20):
    # tiền trả nhà cung cấp/mua hàng/công nợ là GIÁ VỐN (đã ở COGS), không phải
    # chi phí quản lý → tránh đếm 2 lần nếu kế toán lỡ ghi vào chi_phi_phat_sinh.
    # Lương QL: payroll (hcns) là nguồn chuẩn; nếu payroll RỖNG → lấy từ chi_phi
    # 'Thanh Toán Lương'/'Ứng Lương' (nhom='quan_ly') để lương RA ĐÚNG DÒNG LƯƠNG,
    # KHÔNG lẫn vào "khác" (anh Quang chốt 2026-08-27).
    ql_luong_from_chiphi = round(_sum_cp_phat_sinh_filter(
        db, tu, den, nhom="quan_ly", name_like_any=["%lương%", "%luong%"],
    ), 2)
    _QL_EXCLUDE_NCC = [
        "%ncc%", "%nhà cung cấp%", "%nha cung cap%",
        "%mua hàng%", "%mua hang%", "%công nợ%", "%cong no%",
        # Lương tách ra DÒNG LƯƠNG riêng → không đếm vào "khác"
        "%lương%", "%luong%",
        # Ads/marketing đã gộp vào bh_ads → KHÔNG để lọt vào ql_khac (tránh trừ 2 lần
        # khi khoản quảng cáo bị ghi nhầm nhom='quan_ly'). (LOG-03, 2026-08-28)
        "%marketing%", "%ads%", "%quảng cáo%", "%quang cao%",
        # Hoàn tiền đã trừ ở giảm_trừ DT → không lọt vào chi phí QL (trừ 2 lần). L11
        "%hoàn tiền%", "%hoan tien%",
    ]
    ql_total_ps = round(_sum_cp_phat_sinh_filter(
        db, tu, den, nhom="quan_ly", exclude_name_like=_QL_EXCLUDE_NCC,
        also_ten_khoan=True,  # bắt cả hoàn tiền/lương/ncc ghi ở ten_khoan
    ), 2)
    ql_khac = round(max(0.0, ql_total_ps - (ql_vpp + ql_dao_tao + ql_hoi_hop + ql_qua)), 2)

    ql_bien_phi_tong = round(
        ql_vpp + ql_dao_tao + ql_hoi_hop + ql_qua + ql_khac, 2,
    )

    # Định phí QL — Phase 5C: dòng filter dùng method-only variant
    ql_thue_vp = round(_sum_co_dinh_duong_thang_method_only(
        db, thang, "quan_ly",
        name_like_any=["%thuê%", "%thue%"],
    ), 2)
    ql_dien_nuoc = round(_sum_co_dinh_duong_thang_method_only(
        db, thang, "quan_ly",
        name_like_any=["%điện%", "%dien%", "%nước%", "%nuoc%"],
    ), 2)
    ql_internet = round(_sum_co_dinh_duong_thang_method_only(
        db, thang, "quan_ly",
        name_like_any=["%internet%", "%điện thoại%", "%dien thoai%"],
    ), 2)
    ql_dv_kt = round(_sum_co_dinh_duong_thang_method_only(
        db, thang, "quan_ly",
        name_like_any=["%kế toán%", "%ke toan%", "%luật%", "%luat%"],
    ), 2)
    # Dòng LƯƠNG QL cuối cùng: ưu tiên payroll (đã gộp BHXH); payroll rỗng → chi_phi.
    luong_ql_line = luong_cb_ql_with_bhxh if pr_ql["luong_co_ban"] > 0 else ql_luong_from_chiphi
    ql_khau_hao = round(_sum_khau_hao(db, thang, "quan_ly"), 2)
    # QL định phí khác (gồm rows method='manual'/'seasonal'/etc + duong_thang
    # không khớp keyword) = total - 4 dòng filter
    ql_co_dinh_total = round(_sum_co_dinh_method_dispatcher(db, thang, "quan_ly")["tong"], 2)
    ql_dinh_phi_khac = round(
        max(0.0, ql_co_dinh_total - (ql_thue_vp + ql_dien_nuoc + ql_internet + ql_dv_kt)), 2,
    )

    ql_dinh_phi_tong = round(
        luong_ql_line + ql_thue_vp + ql_dien_nuoc
        + ql_internet + ql_khau_hao + ql_dv_kt + ql_dinh_phi_khac, 2,
    )

    cp_quan_ly = {
        "bien_phi": {
            "vpp": ql_vpp,
            "dao_tao": ql_dao_tao,
            "hoi_hop_cong_tac": ql_hoi_hop,
            "qua_bieu": ql_qua,
            "khac": ql_khac,
            "tong": ql_bien_phi_tong,
        },
        "dinh_phi": {
            "luong_co_ban_hcns_kt_ceo": luong_ql_line,
            "thue_vp": ql_thue_vp,
            "dien_nuoc_vp": ql_dien_nuoc,
            "internet_dien_thoai": ql_internet,
            "khau_hao_tscd_ql": ql_khau_hao,
            "dich_vu_kt_luat": ql_dv_kt,
            "phi_khac": ql_dinh_phi_khac,  # Phase 5C: rows method!=duong_thang OR ko match keyword
            "tong": ql_dinh_phi_tong,
        },
        "tong": round(ql_bien_phi_tong + ql_dinh_phi_tong, 2),
    }

    # ── 7. LN thuần HĐKD ─────────────────────────────────────────────────────
    ln_thuan_hdkd = round(
        ln_gop + dt_tai_chinh
        - cp_tai_chinh["tong"]
        - cp_ban_hang["tong"]
        - cp_quan_ly["tong"],
        2,
    )

    # ── 8. Thu nhập khác / CP khác ───────────────────────────────────────────
    thu_nhap_khac_711 = round(_sum_cp_khac_journal(db, tu, den, "711"), 2)
    thu_nhap_khac = thu_nhap_khac_711

    # CP khác = nhom='khac' NHƯNG loại: hoàn tiền (→ giảm trừ DT), tạm ứng (chưa phải
    # chi phí), marketing/ads/quảng cáo (→ đã gộp vào bh_ads). Tránh đếm sai/2 lần.
    cp_khac_ps = round(_sum_cp_phat_sinh_filter(
        db, tu, den, nhom="khac",
        exclude_name_like=[
            "%hoàn tiền%", "%hoan tien%",
            "%tạm ứng%", "%tam ung%",
            "%marketing%", "%ads%", "%quảng cáo%", "%quang cao%",
        ],
        also_ten_khoan=True,
    ), 2)
    cp_khac_811 = round(_sum_cp_khac_journal(db, tu, den, "811"), 2)
    cp_khac = round(cp_khac_ps + cp_khac_811, 2)

    # ── 9. LN trước thuế / Thuế / LNST ────────────────────────────────────────
    ln_truoc_thue = round(ln_thuan_hdkd + thu_nhap_khac - cp_khac, 2)
    thue_tndn = round(ln_truoc_thue * TAX_RATE_TNDN, 2) if ln_truoc_thue > 0 else 0.0
    lnst = round(ln_truoc_thue - thue_tndn, 2)

    # ── 10. Metadata ─────────────────────────────────────────────────────────
    metadata = {
        "so_don_hoan_thanh_trong_ky": _count_orders_hoan_thanh(db, tu, den),
        "so_giao_dich_chi_phi": _count_chi_phi_giao_dich(db, tu, den, thang),
        "phan_bo_dinh_phi_count": _count_co_dinh_phan_bo(db, thang),
        "khau_hao_tscd_count": _count_khau_hao_log(db, thang),
    }

    return {
        "thang": thang,
        "tu_ngay": str(tu),
        "den_ngay": str(den),

        # 1-2: Doanh thu
        "doanh_thu": {
            "dt_thuc_hien": round(dt_thuc_hien, 2),
            "chiet_khau": chiet_khau,
            "giam_tru": giam_tru_dt,
            "dt_thuan": dt_thuan,
        },
        "dt_thuan": dt_thuan,  # alias top-level cho yearly aggregation

        # 3: COGS + LN gộp
        "cogs": cogs,
        "ln_gop": ln_gop,

        # 4-5: Tài chính
        "dt_tai_chinh": dt_tai_chinh,
        "cp_tai_chinh": cp_tai_chinh,

        # 6: CP bán hàng
        "cp_ban_hang": cp_ban_hang,

        # 7: CP quản lý
        "cp_quan_ly": cp_quan_ly,

        # 8: LN thuần HĐKD
        "ln_thuan_hdkd": ln_thuan_hdkd,

        # 9-10: Khác
        "thu_nhap_khac": thu_nhap_khac,
        "cp_khac": cp_khac,

        # 11-12-13: Kết quả
        "ln_truoc_thue": ln_truoc_thue,
        "thue_tndn": thue_tndn,
        "lnst": lnst,

        "metadata": metadata,
    }
