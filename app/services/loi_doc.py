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


def mo_ta_loi(chi_tiet: str) -> str:
    """Câu tiếng Việt cho người đọc báo cáo — thông báo gốc của Postgres là tiếng Anh."""
    m = re.search(r'relation "([^"]+)" does not exist', chi_tiet)
    if m:
        return f"Không có bảng {m.group(1)}"
    m = re.search(r'column "?([^" ]+)"? does not exist', chi_tiet)
    if m:
        return f"Không có cột {m.group(1)}"
    return "Câu truy vấn lỗi: " + chi_tiet[:160]
