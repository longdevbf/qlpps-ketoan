"""HCNS employees lookup helpers — dùng chung cho 6 app.

Pattern: same-DB lazy-import (xem `marketing/app/routers/leads.py:chuyen_kd`).

Các app khác (baogia, marketing, muahang, ketoan, saleadmin, hcns) gọi:
    from shared.services.employees import lookup_employee, bulk_lookup
    info = lookup_employee(db, "kd_cuong")          # → dict | None
    infos = bulk_lookup(db, ["kd_cuong", "mkt_an"]) # → {username: dict}

Schema decision:
    Match qua cột `hcns.employees.username` (đã có UNIQUE INDEX), dùng chính
    `shared.users.username` để nối. Nếu thiếu fallback qua email
    `{username}@papasan.local` để khớp với convention seed.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session


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
