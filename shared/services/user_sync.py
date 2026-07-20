"""Sync `hcns.employees` ↔ `shared.users`.

Helpers:
    - `ensure_user_for_employee(db, employee, *, audit_user=None)` →
        Tạo `shared.users` mới hoặc link vào user đã tồn tại theo `employee.username`
        (auto-gen `ma_nv.lower()` nếu employee chưa có username).
        Trả `(user, action)` với `action ∈ {"created", "linked", "updated_apps", "noop"}`.

    - `set_user_active(db, username, active)` →
        Toggle `users.active` theo username. Trả True nếu đã đổi state, False
        nếu user không tồn tại HOẶC đã ở đúng state đó (idempotent).

Lazy-imports (`shared.models.User`, `shared.auth.hash_password`,
`shared.services.role_map`) để tránh circular import giữa các app.
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple, TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

if TYPE_CHECKING:  # pragma: no cover
    from shared.models import User as UserType

_log = logging.getLogger("shared.user_sync")


# Default password cho NV mới — admin yêu cầu NV đổi sau lần đăng nhập đầu.
DEFAULT_NEW_USER_PASSWORD = "nv@123"

# Trạng thái → ý nghĩa active
TRANG_THAI_INACTIVE = {"Nghỉ việc", "Đã nghỉ", "Sa thải", "nghi_viec", "Thôi việc"}
TRANG_THAI_ACTIVE = {"Đang làm", "Tạm nghỉ", "dang_lam"}


def is_inactive_status(trang_thai: Optional[str]) -> bool:
    """True nếu trang_thai biểu thị NV nghỉ việc/sa thải."""
    return (trang_thai or "").strip() in TRANG_THAI_INACTIVE


def is_active_status(trang_thai: Optional[str]) -> bool:
    """True nếu trang_thai biểu thị NV đang làm việc bình thường."""
    return (trang_thai or "").strip() in TRANG_THAI_ACTIVE


def derive_username(employee) -> str:
    """Lấy username để link với shared.users.

    Ưu tiên `employee.username` đã set sẵn, fallback `ma_nv.lower()`.
    """
    if getattr(employee, "username", None):
        return str(employee.username).lower()
    return str(getattr(employee, "ma_nv", "") or "").lower()


def ensure_user_for_employee(
    db: Session,
    employee,
    *,
    default_password: str = DEFAULT_NEW_USER_PASSWORD,
) -> Tuple["UserType", str]:
    """Đảm bảo có `shared.users` cho NV này.

    Logic:
        1. Tính username = employee.username || ma_nv.lower().
        2. Nếu chưa tồn tại user → tạo mới với password mặc định + role/apps
           map từ `phong_ban` + `chuc_vu`. action="created".
        3. Nếu đã tồn tại → link `employee.username` về user đó. Đồng thời
           sync `role` + `apps` theo phong_ban hiện tại (tránh user cũ giữ
           quyền cũ khi đổi phòng). action="linked" hoặc "updated_apps".
        4. Sync `employee.password_hash` = user.password_hash để keep parity.

    Idempotent: gọi 2 lần liên tiếp lần 2 sẽ trả "noop" / "linked" tùy diff.

    Trả: (user, action). action ∈ {"created", "linked", "updated_apps", "noop"}.
    """
    # Lazy imports để tránh circular giữa shared/hcns/app khác
    from shared.models import User  # noqa: WPS433
    from shared.auth import hash_password  # noqa: WPS433
    from shared.services.role_map import apps_for_employee  # noqa: WPS433

    username = derive_username(employee)
    if not username:
        raise ValueError("Employee thiếu username + ma_nv — không thể sync user")

    # apps = HỢP phòng chính + phòng kiêm nhiệm (phong_ban_phu) → 1 NV nhiều phòng ban
    role, apps = apps_for_employee(
        getattr(employee, "phong_ban", None),
        getattr(employee, "chuc_vu", None),
        getattr(employee, "phong_ban_phu", None),
    )

    existing: Optional[User] = db.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()

    if existing is None:
        password_hash = hash_password(default_password)
        new_user = User(
            username=username,
            password_hash=password_hash,
            full_name=(employee.ho_ten or username),
            email=getattr(employee, "email", None) or None,
            phone=getattr(employee, "dien_thoai", None) or None,
            role=role,
            apps=apps,
            active=True,
        )
        db.add(new_user)
        # Cập nhật employee → link username + same hash để login local cũng hoạt động
        employee.username = username
        employee.password_hash = password_hash
        db.commit()
        db.refresh(new_user)
        _log.info(
            "ensure_user_for_employee: CREATED user=%s role=%s apps=%s for ma_nv=%s",
            username, role, apps, getattr(employee, "ma_nv", "?"),
        )
        return new_user, "created"

    # User đã tồn tại → link + sync apps/role theo phong_ban mới
    changed = False
    action = "linked"

    # Nếu apps/role đã đúng + employee.username đã link → noop
    cur_apps = list(existing.apps or [])
    if set(cur_apps) != set(apps) or existing.role != role:
        existing.role = role
        existing.apps = apps
        changed = True
        action = "updated_apps"

    if not employee.username or employee.username != username:
        employee.username = username
        changed = True

    # Sync password_hash (1 chiều: nếu employee chưa có hash, dùng của user hiện tại)
    if not employee.password_hash and existing.password_hash:
        employee.password_hash = existing.password_hash
        changed = True

    # Reactivate user nếu employee đang ở trạng thái active và user đang inactive.
    # Edge case: re-create employee sau khi DELETE (user trước đó bị set inactive).
    emp_status = getattr(employee, "trang_thai", None)
    if is_active_status(emp_status) and not existing.active:
        existing.active = True
        changed = True
        if action == "linked":
            action = "updated_apps"  # mark as changed even nếu role/apps trùng

    if changed:
        db.commit()
        db.refresh(existing)
        _log.info(
            "ensure_user_for_employee: %s user=%s role=%s apps=%s for ma_nv=%s",
            action.upper(), username, role, apps, getattr(employee, "ma_nv", "?"),
        )
        return existing, action

    return existing, "noop"


def set_user_active(db: Session, username: Optional[str], active: bool) -> bool:
    """Toggle `shared.users.active` theo username (idempotent).

    Trả:
        True  — đã đổi state (commit thành công).
        False — user không tồn tại, hoặc đã ở đúng state (no-op).
    """
    if not username:
        return False
    from shared.models import User  # noqa: WPS433

    user: Optional[User] = db.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()
    if user is None:
        _log.info("set_user_active: user=%s không tồn tại — bỏ qua", username)
        return False

    if bool(user.active) == bool(active):
        return False  # already in desired state

    user.active = bool(active)
    db.commit()
    _log.info("set_user_active: user=%s → active=%s", username, active)

    # Anh Quang 2026-06-13: Invalidate Redis cache `user:active:{username}` ngay
    # để middleware auth không phải chờ TTL 60s. Khi HCNS đánh dấu Đã nghỉ →
    # NV đó refresh trang là 401 INSTANT.
    try:
        import os
        import redis as _redis_mod
        url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        r = _redis_mod.Redis.from_url(
            url, socket_timeout=2, socket_connect_timeout=2, decode_responses=True,
        )
        r.delete(f"user:active:{username}")
    except Exception as e:
        _log.warning("Redis invalidate user:active:%s fail: %s", username, e)

    return True


__all__ = [
    "DEFAULT_NEW_USER_PASSWORD",
    "TRANG_THAI_ACTIVE",
    "TRANG_THAI_INACTIVE",
    "is_active_status",
    "is_inactive_status",
    "derive_username",
    "ensure_user_for_employee",
    "set_user_active",
]
