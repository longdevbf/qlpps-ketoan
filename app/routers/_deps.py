"""Shared dependencies cho routers Kế Toán.

Phân quyền: `admin` / `ceo` / `assistant_ceo` / `manager` / `kt` được view/edit.
Reject 403 cho `kd` / `mkt` / `mh` / `sa` / `hr` / `nhan_vien`.
"""
from fastapi import Depends, HTTPException, status

from shared.auth import JWTPayload, require_app


# `kt` = NV chuyên trách Kế Toán (auto-sync từ HCNS phong_ban='Kế Toán').
_KETOAN_ROLES = ("admin", "ceo", "assistant_ceo", "manager", "kt")


def require_ketoan_user(user: JWTPayload = Depends(require_app("ketoan"))) -> JWTPayload:
    """Yêu cầu user có quyền vào app ketoan + role hợp lệ."""
    if user.role not in _KETOAN_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Role {user.role!r} không có quyền truy cập app Kế Toán",
        )
    return user
