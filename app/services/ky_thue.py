"""Kỳ tính thuế (tháng 'YYYY-MM' / quý 'Qn-YYYY') + hạn nộp theo Luật Quản lý thuế 38/2019/QH14.

- Khai theo tháng: hạn nộp tờ khai + tiền thuế ngày 20 tháng sau (Điều 44.1a).
- Khai theo quý: ngày cuối cùng của tháng đầu quý sau (Điều 44.1b).
- TNDN tạm nộp quý: chậm nhất ngày 30 tháng đầu quý sau (Điều 55.1).
Hạn rơi vào ngày nghỉ được lùi sang ngày làm việc kế tiếp — KHÔNG tính ở đây
(không có lịch nghỉ lễ trong hệ thống), hiển thị đúng ngày luật định.
"""
import calendar
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status

MUI_GIO = ZoneInfo("Asia/Ho_Chi_Minh")
NGAY_HAN_KHAI_THANG = 20
NGAY_HAN_TAM_NOP_TNDN = 30

_RE_THANG = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_RE_QUY = re.compile(r"^Q([1-4])-(\d{4})$")


def hom_nay() -> date:
    return datetime.now(MUI_GIO).date()


def thang_nay() -> str:
    return hom_nay().strftime("%Y-%m")


def quy_cua(d: date) -> str:
    return f"Q{(d.month - 1) // 3 + 1}-{d.year}"


def cuoi_thang(nam: int, thang: int) -> date:
    return date(nam, thang, calendar.monthrange(nam, thang)[1])


def cong_thang(nam: int, thang: int, n: int) -> tuple[int, int]:
    """(nam, thang) + n tháng."""
    k = nam * 12 + (thang - 1) + n
    return k // 12, k % 12 + 1


def la_ky_thang(ky: str) -> bool:
    return bool(_RE_THANG.match(ky or ""))


def khoang_ky(ky: str) -> tuple[date, date]:
    """'YYYY-MM' hoặc 'Qn-YYYY' → (ngày đầu, ngày cuối). Sai định dạng → 400."""
    m = _RE_THANG.match(ky or "")
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return date(y, mo, 1), cuoi_thang(y, mo)
    q = _RE_QUY.match(ky or "")
    if q:
        n, y = int(q.group(1)), int(q.group(2))
        return date(y, 3 * n - 2, 1), cuoi_thang(y, 3 * n)
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kỳ phải có dạng YYYY-MM hoặc Qn-YYYY")


def kiem_quy(quy: str) -> str:
    if not _RE_QUY.match(quy or ""):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Quý phải có dạng Qn-YYYY")
    return quy


def kiem_thang(thang: str) -> str:
    if not _RE_THANG.match(thang or ""):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tháng phải có dạng YYYY-MM")
    return thang


def cac_thang_cua_quy(quy: str) -> list[str]:
    n, y = int(quy[1]), int(quy[3:])
    return [f"{y}-{m:02d}" for m in range(3 * n - 2, 3 * n + 1)]


def han_nop_khai(ky: str) -> date:
    """Hạn nộp tờ khai/tiền thuế của kỳ (tháng → ngày 20 tháng sau, quý → cuối tháng đầu quý sau)."""
    _, den = khoang_ky(ky)
    y, m = cong_thang(den.year, den.month, 1)
    if la_ky_thang(ky):
        return date(y, m, NGAY_HAN_KHAI_THANG)
    return cuoi_thang(y, m)


def han_tam_nop_tndn(quy: str) -> date:
    _, den = khoang_ky(quy)
    y, m = cong_thang(den.year, den.month, 1)
    return date(y, m, NGAY_HAN_TAM_NOP_TNDN)
