"""Cross-schema reader — đọc bảng từ hcns/muahang/marketing.

Sprint 1: dùng raw SQL `db.execute(text(...))` để tránh phụ thuộc cứng vào models 3 app khác
(hcns models có thể chưa tồn tại tại thời điểm chạy). Khi 3 app stable, có thể swap qua import models.

KHÔNG sửa code 3 app khác — chỉ READ-ONLY query.
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError, OperationalError
from sqlalchemy.orm import Session


def _safe_scalar(db: Session, sql: str, **params) -> Decimal:
    """Execute scalar SUM, fail-soft trả 0 nếu bảng không tồn tại."""
    try:
        result = db.execute(text(sql), params).scalar()
        return Decimal(result or 0)
    except (ProgrammingError, OperationalError):
        # Bảng chưa có hoặc cột chưa khớp → trả 0, không raise
        db.rollback()
        return Decimal(0)


def read_luong_total(
    db: Session,
    thang: Optional[str] = None,             # 'YYYY-MM'
) -> Decimal:
    """Tổng lương từ `hcns.payroll` theo tháng.

    Schema giả định (HCNS Sprint 1 sẽ confirm):
        hcns.payroll(thang TEXT, thuc_linh NUMERIC, ...)
    """
    if not thang:
        return Decimal(0)
    sql = """
        SELECT COALESCE(SUM(thuc_linh), 0)
        FROM hcns.payroll
        WHERE thang = :thang
    """
    return _safe_scalar(db, sql, thang=thang)


# Định nghĩa "đơn hàng" cộng vào doanh thu Dashboard (công thức cũ) — dùng chung cho tổng
# (read_don_hang_total) và chuỗi theo tháng (read_don_hang_by_thang) để hai số luôn khớp.
_DON_HANG_GIA_TRI = (
    "COALESCE((ncc_totals->>selected_ncc_id)::numeric, 0) - COALESCE(discount, 0)"
)
_DON_HANG_WHERE = """
        WHERE created_at::date >= :tu AND created_at::date <= :den
          AND status IN ('Hoàn Thành', 'Đã có hàng', 'Đặt hàng', 'Đang SX', 'Đã Duyệt Mua')
"""


def read_don_hang_total(
    db: Session,
    tu_ngay: date,
    den_ngay: date,
) -> Decimal:
    """Tổng giá trị đơn hàng `muahang.purchase_orders` đã hoàn thành trong khoảng.

    Sprint 1: V1 dùng cột 'Tổng đơn (đ)' từ sheet — V2 muahang chưa expose total flat
    trong PurchaseOrder. Tính từ items → join + sum nếu có cột `gia_chot`.
    Fallback: COUNT(*) → 0 nếu không có cột phù hợp.
    """
    sql = f"""
        SELECT COALESCE(SUM({_DON_HANG_GIA_TRI}), 0)
        FROM muahang.purchase_orders
        {_DON_HANG_WHERE}
    """
    return _safe_scalar(db, sql, tu=tu_ngay, den=den_ngay)


def read_don_hang_by_thang(
    db: Session,
    tu_ngay: date,
    den_ngay: date,
) -> dict[str, Decimal]:
    """Cùng định nghĩa read_don_hang_total, gộp theo tháng 'YYYY-MM' (fail-soft {})."""
    sql = f"""
        SELECT to_char(created_at::date, 'YYYY-MM') AS thang,
               COALESCE(SUM({_DON_HANG_GIA_TRI}), 0)
        FROM muahang.purchase_orders
        {_DON_HANG_WHERE}
        GROUP BY 1
    """
    try:
        rows = db.execute(text(sql), {"tu": tu_ngay, "den": den_ngay}).all()
    except (ProgrammingError, OperationalError):
        db.rollback()
        return {}
    return {str(k): Decimal(v or 0) for k, v in rows}


def read_ads_total(
    db: Session,
    tu_ngay: date,
    den_ngay: date,
) -> Decimal:
    """Tổng chi phí ads `marketing.ads_cost` trong khoảng ngày."""
    sql = """
        SELECT COALESCE(SUM(chi_phi), 0)
        FROM marketing.ads_cost
        WHERE ngay >= :tu AND ngay <= :den
    """
    return _safe_scalar(db, sql, tu=tu_ngay, den=den_ngay)
