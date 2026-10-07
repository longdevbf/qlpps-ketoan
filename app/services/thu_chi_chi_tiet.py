"""Đọc chéo app cho popup chi tiết màn Thu chi (/ketoan/thu-chi): khách của đơn, đề xuất chi nguồn.

Hai nguồn thuộc app khác, đọc bằng SQL thô có bind param (luật cross-app — không import ORM app khác):
  - baogia.quotes            khách của đơn: quote_number = ketoan.doanh_thu.ma_don
  - shared.expense_requests  đề xuất chi đã bấm Chi: chi_phi_id = ketoan.chi_phi_phat_sinh.id
    (shared/routers/duyet_chi.py, chi_expense: `rec.chi_phi_id = cp.id`). KHÔNG nối qua cột ref_dntt:
    ref_dntt = 'DNTT-{id}' trỏ sang saleadmin.denghitt — Đề nghị TT của Sale Admin
    (services/from_saleadmin.py).

Fail-soft nhưng KHÔNG im lặng: bảng/cột thiếu trên máy này → log WARNING + trả cờ doc_duoc=False để
giao diện nói "chưa đọc được", thay vì trả None trông y hệt "không có dữ liệu". Mỗi câu chạy trong
SAVEPOINT (begin_nested): câu lỗi chỉ huỷ phần của nó, transaction của request vẫn dùng tiếp được.
"""
import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# quote_number theo thiết kế là duy nhất; ORDER BY id DESC chỉ để chắc chắn ra MỘT dòng
# nếu dữ liệu cũ bị trùng.
_SQL_KHACH = text("""
    SELECT customer_name, customer_phone, customer_address, salesperson
    FROM baogia.quotes
    WHERE quote_number = :ma
    ORDER BY id DESC
    LIMIT 1
""")

# Các cột nguoi_thu_huong … ma_don có từ migration shared 0049 (05/10/2026); chung_tu_urls từ 0037.
_SQL_DE_XUAT = text("""
    SELECT id, tieu_de, ho_ten, phong_ban, ngay_de_xuat,
           nguoi_thu_huong, so_tk_nhan, ngan_hang_nhan, hinh_thuc, ma_don, loai_chi_phi,
           chung_tu_url, chung_tu_urls, ho_ten_nguoi_duyet, ngay_duyet
    FROM shared.expense_requests
    WHERE chi_phi_id = :cp
    ORDER BY id DESC
    LIMIT 1
""")


def _doc_mot_dong(db: Session, cau: Any, tham_so: dict, nguon: str) -> tuple[Optional[dict], bool]:
    """Chạy một câu đọc chéo app trong SAVEPOINT. Trả (dòng | None, đọc được hay không)."""
    try:
        with db.begin_nested():
            dong = db.execute(cau, tham_so).mappings().first()
    except (ProgrammingError, OperationalError) as e:
        logger.warning("Không đọc được %s (tham số %s): %s", nguon, tham_so, getattr(e, "orig", e))
        return None, False
    return (dict(dong) if dong else None), True


def doc_khach_theo_don(db: Session, ma_don: Optional[str]) -> tuple[Optional[dict], bool]:
    """Khách của đơn báo giá mang mã `ma_don`.

    (None, True) = đọc được nhưng không có đơn đó, hoặc phiếu không có mã đơn.
    """
    ma = (ma_don or "").strip()
    if not ma:
        return None, True
    return _doc_mot_dong(db, _SQL_KHACH, {"ma": ma}, "baogia.quotes")


def doc_de_xuat_cua_chi_phi(db: Session, chi_phi_id: int) -> tuple[Optional[dict], bool]:
    """Đề xuất chi (shared.expense_requests) đã sinh ra dòng chi phí này qua nút Chi — None nếu không có."""
    dong, doc_duoc = _doc_mot_dong(db, _SQL_DE_XUAT, {"cp": chi_phi_id}, "shared.expense_requests")
    if dong:
        # chung_tu_url cũ = phần tử đầu của danh sách đa file (mig 0037) → gộp lại, bỏ trùng, bỏ rỗng.
        ds = [u for u in (dong.pop("chung_tu_urls", None) or []) if isinstance(u, str) and u.strip()]
        cu = dong.pop("chung_tu_url", None)
        if cu and cu not in ds:
            ds.insert(0, cu)
        dong["chung_tu_urls"] = ds
    return dong, doc_duoc
