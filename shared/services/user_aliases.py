"""User aliases — handle data legacy lưu lẫn username và full_name.

Trong V2, các field owner như `customers.kd_nhan`, `quotes.salesperson`,
`leads.kd_nhan` lưu MIX:
- Sometimes username (nv26011)
- Sometimes full_name từ shared.users (Quang Linh)
- Sometimes ho_ten từ hcns.employees (Nguyễn Quang Linh) — có thể khác full_name

Filter strict `field == user.username` → user mất data legacy. Helper này trả
list TẤT CẢ alias để filter dùng `.in_(...)`.

Cache: per-request (không lru_cache global vì user có thể đổi tên).
"""
from __future__ import annotations

from typing import Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.auth import JWTPayload


def user_aliases_for_usernames(
    db: Session, usernames: Sequence[str],
) -> list[str]:
    """Trả TẤT CẢ alias cho list username — gồm username + full_name + ho_ten.

    Fail-soft: nếu shared.users hoặc hcns.employees không tồn tại / lỗi,
    fallback về list username gốc.
    """
    cleaned = [u for u in usernames if u]
    if not cleaned:
        return []
    aliases: set[str] = set(cleaned)
    try:
        rows = db.execute(
            text(
                "SELECT username, full_name FROM shared.users "
                "WHERE username = ANY(:u)"
            ),
            {"u": list(cleaned)},
        ).all()
        for _, full in rows:
            if full:
                aliases.add(full)
    except Exception:
        pass
    try:
        rows = db.execute(
            text(
                "SELECT username, ho_ten FROM hcns.employees "
                "WHERE username = ANY(:u)"
            ),
            {"u": list(cleaned)},
        ).all()
        for _, ho_ten in rows:
            if ho_ten:
                aliases.add(ho_ten)
    except Exception:
        pass
    return list(aliases)


def user_aliases(db: Session, user: JWTPayload) -> list[str]:
    """Tất cả alias của user hiện tại — dùng cho filter NV thường."""
    return user_aliases_for_usernames(db, [user.username])
