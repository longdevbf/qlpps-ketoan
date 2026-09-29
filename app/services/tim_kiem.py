"""Tìm kiếm KHÔNG phân biệt dấu + hoa/thường cho ô tìm của người dùng (anh Quang 28/09/2026).

DB PostgreSQL chạy collation/ctype "C" → ILIKE / lower() chỉ hạ được chữ ASCII: gõ "chiến" không ra
"CHIẾN PHƯƠNG", "thịnh" không ra "Anh THỊNH". Mọi ô tìm của người dùng so khớp qua

    ketoan.bo_dau(<cột>) LIKE '%<từ khoá đã bỏ dấu, đã thoát \\ % _>%'

`ketoan.bo_dau(text)` là hàm SQL IMMUTABLE tạo ở `tim_kiem_schema.py` (chỉ hàm có sẵn: normalize + lower + translate,
KHÔNG dùng extension unaccent). Quy tắc — `bo_dau_py()` ở đây làm y hệt, dựng từ cùng hằng số nên luôn đồng nhất:
    1. normalize(NFD): tách mọi chữ có dấu thành chữ gốc ASCII + dấu kết hợp ("ế" → "e" + U+0302 + U+0301),
       nên cả 134 chữ tiếng Việt có dấu (a/ă/â, e/ê, i, o/ô/ơ, u/ư, y × 5 dấu, hoa lẫn thường) về chữ gốc;
       văn bản vốn đã ở dạng tách (dán từ macOS/Word) cũng xử lý đúng.
    2. lower(): chữ hoa ASCII → thường (locale "C" chỉ hạ ASCII — sau bước 1 mọi chữ tiếng Việt đã là ASCII).
    3. translate(): đ/Đ (+ ð/Ð hay gõ nhầm, có trong dữ liệu thật) → d; xoá các dấu kết hợp.
Vì sao không translate() thẳng 134 chữ có dấu: translate dò cả chuỗi "từ" cho MỖI ký tự → đo trên 40k khách hàng
(2 cột) mất ~510 ms so với ~100 ms của cách NFD ở trên (ILIKE cũ ~5 ms).

Ánh xạ từng ký tự nên chuỗi nào ILIKE khớp trước đây vẫn khớp (gõ đúng nguyên văn không mất kết quả); riêng % và _
trong từ khoá giờ là ký tự thường, không còn là ký tự đại diện.

KHÔNG dùng cho các chỗ ILIKE khớp/ghép dữ liệu nội bộ (phân loại 'cọc'/'thanh toán', ghép tên sản phẩm, tiền tố
bình luận "[BG …]", từ khoá phân loại dòng tiền…) — những chỗ đó giữ nguyên hành vi cũ.
"""
from __future__ import annotations

import logging
import threading
import unicodedata
from typing import Any, Iterable, Optional

from sqlalchemy import Text, func, or_
from sqlalchemy.sql.elements import ColumnElement

_LOG = logging.getLogger(__name__)

TEN_HAM_SQL = "ketoan.bo_dau"

# Dấu kết hợp bị xoá sau NFD: 8 dấu tiếng Việt (huyền, sắc, mũ, ngã, trăng, hỏi, móc, nặng)
# + 4 dấu hay gặp trong tên nước ngoài có trong dữ liệu (¨ ü, ˚ å, ˇ š, ¸ ç).
DAU_KET_HOP = "".join(chr(c) for c in (
    0x0300, 0x0301, 0x0302, 0x0303, 0x0306, 0x0309, 0x031B, 0x0323,
    0x0308, 0x030A, 0x030C, 0x0327,
))
CHU_D = "đĐðÐ"   # đ Đ ð Ð — không có dạng tách NFD nên phải đổi riêng
_ASCII_HOA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

_BANG_PY = str.maketrans(_ASCII_HOA + CHU_D, _ASCII_HOA.lower() + "d" * len(CHU_D), DAU_KET_HOP)
_KY_TU_THOAT = "\\"   # ký tự thoát mặc định của LIKE trong PostgreSQL


def bo_dau_py(chuoi: Optional[str]) -> str:
    """Chữ thường không dấu — CÙNG quy tắc với ketoan.bo_dau() (SQL): NFD → hạ ASCII → đ→d, xoá dấu kết hợp."""
    return unicodedata.normalize("NFD", chuoi or "").translate(_BANG_PY)


def mau_like(tu_khoa: str) -> str:
    """Mẫu LIKE '%<từ khoá bỏ dấu>%' — thoát \\ % _ để chúng là ký tự thường (không phải ký tự đại diện)."""
    t = bo_dau_py(tu_khoa.strip())
    for ky_tu in (_KY_TU_THOAT, "%", "_"):
        t = t.replace(ky_tu, _KY_TU_THOAT + ky_tu)
    return f"%{t}%"


def khop_khong_dau(cot: Any, tu_khoa: str) -> ColumnElement[bool]:
    """Biểu thức SQLAlchemy: ketoan.bo_dau(cot) LIKE '%tu_khoa%' (không phân biệt dấu, hoa/thường)."""
    _dam_bao_ham_mot_lan()
    return func.ketoan.bo_dau(cot, type_=Text).like(mau_like(tu_khoa), escape=_KY_TU_THOAT)


def khop_mot_trong(cac_cot: Iterable[Any], tu_khoa: str) -> ColumnElement[bool]:
    """OR của `khop_khong_dau` trên nhiều cột (vd mã OR tên)."""
    return or_(*[khop_khong_dau(c, tu_khoa) for c in cac_cot])


def sql_khop(cac_cot: Iterable[str], ten_tham_so: str = "kw") -> str:
    """Mảnh SQL thuần cho text(): "(ketoan.bo_dau(c1) LIKE :kw OR …)". Giá trị tham số = mau_like(tu_khoa)."""
    _dam_bao_ham_mot_lan()
    return "(" + " OR ".join(f"{TEN_HAM_SQL}({c}) LIKE :{ten_tham_so}" for c in cac_cot) + ")"


def chua_khong_dau(chuoi: Optional[str], tu_khoa: Optional[str]) -> bool:
    """Lọc trong Python (danh sách đã nạp): chuỗi có chứa từ khoá không — không phân biệt dấu, hoa/thường."""
    t = bo_dau_py((tu_khoa or "").strip())
    return not t or t in bo_dau_py(chuoi)


# ─── Bảo đảm hàm SQL tồn tại ─────────────────────────────────────────────────
# Lifespan app/main.py gọi tim_kiem_schema.dam_bao_ham_bo_dau(engine) lúc khởi động; lần gọi lười dưới đây là lưới
# an toàn (mỗi tiến trình chạy tối đa một lần thành công) để ô tìm không vỡ 500 nếu lifespan chưa gắn / lỗi thoáng qua.
_da_co_ham = False
_khoa = threading.Lock()


def _dam_bao_ham_mot_lan() -> None:
    global _da_co_ham
    if _da_co_ham:
        return
    with _khoa:
        if _da_co_ham:
            return
        try:
            from shared.db import engine
            from .tim_kiem_schema import dam_bao_ham_bo_dau
            dam_bao_ham_bo_dau(engine)
            _da_co_ham = True
        except Exception as e:  # noqa: BLE001 — fail-soft: truy vấn sau sẽ tự báo lỗi nếu hàm thật sự thiếu
            _LOG.warning("Không tạo được hàm %s: %s", TEN_HAM_SQL, e)
