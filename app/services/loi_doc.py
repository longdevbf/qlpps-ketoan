"""Phân biệt "kỳ này không có số" với "không đọc được dữ liệu" trong các báo cáo.

Trước 07/10/2026 các hàm `_safe_scalar` / `_safe_rows` bắt cả `OperationalError` lẫn
`ProgrammingError` rồi trả 0 — mất kết nối DB trông y hệt một kỳ không phát sinh gì.

Quy ước mới:
  - `OperationalError` (mất kết nối, hết thời gian chờ, DB tắt) → KHÔNG bắt nữa, để nổi lên
    error handler chung (`shared/middleware/errors.py` trả 500 `database_error`) → màn hình
    hiện khối lỗi + nút Thử lại thay vì một bảng toàn số 0.
  - `ProgrammingError` (bảng/cột chưa có — vd schema app khác chưa migrate) → vẫn trả giá trị
    mặc định để báo cáo không chết cả trang, nhưng GHI LẠI vào danh sách lỗi của request; endpoint
    báo cáo trả danh sách đó trong trường `loi_doc_du_lieu` để giao diện cảnh báo "số 0 ở đây
    không phải số thật".

Danh sách lỗi sống trong một ContextVar — *biến ngữ cảnh: mỗi request (mỗi luồng xử lý) có bản
riêng, không lẫn sang request khác*. Endpoint nào muốn thu lỗi thì gọi `bat_dau_ghi_loi()` ở đầu;
không gọi thì `ghi_loi_doc()` chỉ log, không thu.
"""
import logging
import re
import sys
from contextvars import ContextVar
from typing import Optional

from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_LOI_DOC: ContextVar[Optional[list[dict]]] = ContextVar("ketoan_loi_doc", default=None)


def bat_dau_ghi_loi() -> list[dict]:
    """Mở danh sách lỗi mới cho request hiện tại và trả về chính danh sách đó."""
    ds: list[dict] = []
    _LOI_DOC.set(ds)
    return ds


def ghi_loi_doc(db: Session, exc: ProgrammingError) -> None:
    """Rollback + log + ghi lỗi đọc (bảng/cột thiếu) vào danh sách của request nếu đang thu.

    Tên hàm gọi tới được lấy tự động để người đọc cảnh báo biết dòng báo cáo nào bị ảnh hưởng.
    """
    db.rollback()
    # Bỏ qua các hàm bọc `_safe_*` để ghi đúng hàm nghiệp vụ đã gọi câu SQL (vd _sum_cogs).
    f = sys._getframe(1)
    while f.f_back is not None and f.f_code.co_name.startswith("_safe"):
        f = f.f_back
    ham = f.f_code.co_name
    chi_tiet = str(getattr(exc, "orig", exc)).strip().splitlines()[0][:300]
    logger.warning("Không đọc được dữ liệu ở %s: %s", ham, chi_tiet)
    ds = _LOI_DOC.get()
    if ds is not None and not any(x["ham"] == ham and x["chi_tiet"] == chi_tiet for x in ds):
        ds.append({"ham": ham, "chi_tiet": chi_tiet, "mo_ta": mo_ta_loi(chi_tiet)})


# Tên nghiệp vụ cho kế toán đọc — luật frontend số 2: không lộ tên kỹ thuật (schema.bảng) ra màn hình.
# Tên kỹ thuật vẫn nằm nguyên trong `chi_tiet` + log máy chủ cho người sửa code.
_TEN_APP = {
    "baogia": "app Báo giá", "saleadmin": "app Sale Admin", "hcns": "app Nhân sự",
    "marketing": "app Marketing", "muahang": "app Mua hàng", "ketoan": "Kế toán", "shared": "dữ liệu dùng chung",
}
_TEN_BANG = {
    "quotes": "báo giá, đơn hàng", "vanchuyen": "vận chuyển", "payroll": "bảng lương",
    "ads_cost": "chi phí quảng cáo", "employees": "danh sách nhân viên", "purchase_orders": "đơn mua hàng",
    "suppliers": "nhà cung cấp", "customers": "khách hàng",
}


def mo_ta_loi(chi_tiet: str) -> str:
    """Câu tiếng Việt cho người đọc báo cáo — thông báo gốc của Postgres là tiếng Anh và kỹ thuật."""
    m = re.search(r'relation "([^"]+)" does not exist', chi_tiet)
    if m:
        schema, _, bang = m.group(1).rpartition(".")
        noi = _TEN_APP.get(schema, "app khác" if schema else "Kế toán")
        return f"Không đọc được dữ liệu {_TEN_BANG.get(bang, 'một bảng')} của {noi}"
    if re.search(r"column .* does not exist", chi_tiet):
        return "Dữ liệu thiếu một cột mà báo cáo cần (chi tiết trong nhật ký máy chủ)"
    return "Một truy vấn của báo cáo bị lỗi (chi tiết trong nhật ký máy chủ)"
