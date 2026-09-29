"""HCNS employees lookup helpers — dùng chung cho 6 app.

Pattern: same-DB lazy-import (xem `marketing/app/routers/leads.py:chuyen_kd`).

Các app khác (baogia, marketing, muahang, ketoan, saleadmin, hcns) gọi:
    from shared.services.employees import lookup_employee, bulk_lookup
    info = lookup_employee(db, "kd_cuong")          # → dict | None
    infos = bulk_lookup(db, ["kd_cuong", "mkt_an"]) # → {username: dict}
    ten = ten_nv(db, [x.nguoi_tao for x in rows])   # → {username: tên hiển thị}

Schema decision:
    Match qua cột `hcns.employees.username` (đã có UNIQUE INDEX), dùng chính
    `shared.users.username` để nối. Nếu thiếu fallback qua email
    `{username}@papasan.local` để khớp với convention seed.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import bindparam, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def _emp_to_dict(emp) -> dict:
    """Convert Employee ORM → dict-safe payload (cross-app)."""
    return {
        "ma_nv": emp.ma_nv,
        "username": emp.username,
        "ho_ten": emp.ho_ten,
        "email": emp.email,
        "sdt": emp.dien_thoai,
        "phong_ban": emp.phong_ban,
        "chuc_vu": emp.chuc_vu,
        "role": emp.role,
        "trang_thai": emp.trang_thai,
        "luong_co_ban": float(emp.luong_co_ban) if isinstance(emp.luong_co_ban, Decimal) else emp.luong_co_ban,
    }


def lookup_employee(db: Session, username: str) -> Optional[dict]:
    """Trả dict info NV theo username, hoặc None nếu không tồn tại.

    Lazy-import `hcns.app.models.Employee` để tránh import vòng khi
    app khác (baogia/marketing/...) khởi động không cần hcns models.
    """
    if not username:
        return None
    from hcns.app.models import Employee  # lazy import (cross-app)

    emp = db.execute(
        select(Employee).where(Employee.username == username)
    ).scalar_one_or_none()

    if emp is None:
        # Fallback: thử match qua email convention `{username}@papasan.local`
        fallback_email = f"{username}@papasan.local"
        emp = db.execute(
            select(Employee).where(Employee.email == fallback_email)
        ).scalar_one_or_none()

    if emp is None:
        return None
    return _emp_to_dict(emp)


def bulk_lookup(db: Session, usernames: Iterable[str]) -> dict[str, dict]:
    """Bulk version: trả {username: info_dict} cho các username tồn tại.

    Username không tồn tại sẽ KHÔNG có key trong dict trả về (caller tự check).
    """
    unames = [u for u in (usernames or []) if u]
    if not unames:
        return {}
    from hcns.app.models import Employee  # lazy import (cross-app)

    rows = db.execute(
        select(Employee).where(Employee.username.in_(unames))
    ).scalars().all()
    found = {emp.username: _emp_to_dict(emp) for emp in rows if emp.username}

    # Fallback email match cho những username chưa tìm thấy
    missing = [u for u in unames if u not in found]
    if missing:
        emails = [f"{u}@papasan.local" for u in missing]
        rows2 = db.execute(
            select(Employee).where(Employee.email.in_(emails))
        ).scalars().all()
        for emp in rows2:
            if not emp.email:
                continue
            uname = emp.email.split("@", 1)[0]
            if uname in missing and uname not in found:
                found[uname] = _emp_to_dict(emp)

    return found


def ten_nv(db: Session, usernames: Iterable[Optional[str]]) -> dict[str, str]:
    """username → tên hiển thị, một câu SQL cho mỗi bảng (18/09/2026).

    Dùng khi trả danh sách ra màn hình: cột `nguoi_tao`, `duyet_boi`, `kd_nhan`…
    lưu username (`nv26025`) là đúng khoá, nhưng người xem cần tên. Backend gọi
    hàm này một lần cho cả trang rồi gắn thêm trường `*_ten` cạnh trường cũ.

    Ưu tiên `hcns.employees.ho_ten` (hồ sơ nhân sự chính thức), thiếu thì
    `shared.users.full_name` (tài khoản không có hồ sơ HCNS như admin). KHÔNG lọc
    trạng thái — NV đã nghỉ vẫn phải ra tên trên bản ghi cũ. So khớp LOWER(TRIM())
    nên 'NV26015' và 'nv26015' đều ra.

    Không tìm thấy → trả lại CHÍNH chuỗi vào: nhiều cột lưu lẫn mã và tên
    (`quotes.salesperson`, `leads.kd_nhan`), giá trị đã là tên thì giữ nguyên.
    Dict trả về giữ khoá y như đầu vào để caller `.get(x.kd_nhan)` được.

    Đọc chéo schema hcns trong SAVEPOINT (`begin_nested`): lỗi thì chỉ hàm này
    fail-soft, transaction bên ngoài vẫn dùng tiếp được — không SAVEPOINT thì
    một SELECT hỏng làm mọi `db.add` sau đó hỏng theo.
    """
    goc = [str(u).strip() for u in (usernames or []) if u and str(u).strip()]
    if not goc:
        return {}
    # Khoá chuẩn hoá → danh sách chuỗi gốc (cùng một NV có thể vào cả 'NV26015' lẫn 'nv26015')
    theo_khoa: dict[str, list[str]] = {}
    for u in goc:
        theo_khoa.setdefault(u.lower(), []).append(u)
    ds = sorted(theo_khoa)
    ten_theo_khoa: dict[str, str] = {}
    try:
        with db.begin_nested():
            # Tra cả `ma_nv` vì một số bảng (lệnh đi đo, công trình) lưu ma_nv chứ không
            # phải username, và 4 NV có ma_nv ≠ username (NV26004 ↔ ceopps). Khớp username
            # được ưu tiên: dòng khớp ma_nv chỉ dùng khi khoá đó chưa có tên.
            rows = db.execute(text(
                "SELECT LOWER(TRIM(username)), LOWER(TRIM(ma_nv)), TRIM(ho_ten) FROM hcns.employees "
                "WHERE (LOWER(TRIM(username)) IN :ds OR LOWER(TRIM(ma_nv)) IN :ds) "
                "AND COALESCE(TRIM(ho_ten), '') <> ''"
            ).bindparams(bindparam("ds", expanding=True)), {"ds": ds}).all()
        ten_theo_khoa.update({u: t for u, _m, t in rows if u in theo_khoa})
        for _u, m, t in rows:
            if m in theo_khoa:
                ten_theo_khoa.setdefault(m, t)
    except SQLAlchemyError as exc:
        log.warning("ten_nv: không đọc được hcns.employees: %s", exc)

    thieu = [k for k in ds if k not in ten_theo_khoa]
    if thieu:
        try:
            with db.begin_nested():
                rows = db.execute(text(
                    "SELECT LOWER(TRIM(username)), TRIM(full_name) FROM shared.users "
                    "WHERE LOWER(TRIM(username)) IN :ds AND COALESCE(TRIM(full_name), '') <> ''"
                ).bindparams(bindparam("ds", expanding=True)), {"ds": thieu}).all()
            for k, t in rows:
                ten_theo_khoa.setdefault(k, t)
        except SQLAlchemyError as exc:
            log.warning("ten_nv: không đọc được shared.users: %s", exc)

    return {u: ten_theo_khoa.get(k, u) for k, cac_u in theo_khoa.items() for u in cac_u}
