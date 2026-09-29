"""Bảng tra mã nhân viên → họ tên, dùng để hiển thị TÊN thay cho mã (nv26006 → Nguyễn Duy Thành).

Nguồn: `shared.users` (username → full_name) và `hcns.employees` (ma_nv / username → ho_ten).
Khoá tra là chữ thường, vì chỗ lưu `nv26006`, chỗ lưu `NV26006`. Cache trong tiến trình
TTL_GIAY giây — danh sách nhân sự đổi rất chậm, mà màn nào cũng gọi.
"""
import re
import time

from sqlalchemy import text
from sqlalchemy.orm import Session

TTL_GIAY = 300
_RE_TK_PHU = re.compile(r"^(nv\d{5})_\d+$")

_SQL_USERS = text(
    "SELECT username, full_name FROM shared.users "
    "WHERE username IS NOT NULL AND COALESCE(full_name, '') <> ''"
)
_SQL_EMPLOYEES = text(
    "SELECT ma_nv, username, ho_ten FROM hcns.employees WHERE COALESCE(ho_ten, '') <> ''"
)

_cache: dict = {"t": 0.0, "map": {}}


def _nap(db: Session) -> dict[str, str]:
    ban_do: dict[str, str] = {}
    for username, ten in db.execute(_SQL_USERS):
        ban_do[username.strip().lower()] = ten.strip()
    # hcns là hồ sơ nhân sự chuẩn → ghi đè tên của shared.users nếu trùng khoá.
    ho_so: dict[str, str] = {}
    for ma_nv, username, ten in db.execute(_SQL_EMPLOYEES):
        for khoa in (ma_nv, username):
            if khoa:
                ho_so[khoa.strip().lower()] = ten.strip()
    ban_do.update(ho_so)
    # Tài khoản phụ "nv26019_2" (full_name hay bị gõ tắt "long", "A") → lấy tên hồ sơ gốc "nv26019".
    for khoa in list(ban_do):
        goc = _RE_TK_PHU.match(khoa)
        if goc and goc.group(1) in ho_so:
            ban_do[khoa] = ho_so[goc.group(1)]
    return ban_do


def ban_do_ten(db: Session) -> dict[str, str]:
    if time.monotonic() - _cache["t"] > TTL_GIAY or not _cache["map"]:
        _cache["map"] = _nap(db)
        _cache["t"] = time.monotonic()
    return _cache["map"]
