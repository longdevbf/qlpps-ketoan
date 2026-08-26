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


# CHỈ CEO được SỬA/XOÁ lệnh thu chi (sổ quỹ, doanh thu, chi phí) — Kế Toán
# (manager/kt) chỉ được TẠO MỚI, không sửa/xoá (anh Quang 2026-08-24, kiểm soát nội bộ).
_CEO_THUCHI_ROLES = ("admin", "ceo", "assistant_ceo")


def require_ceo_thuchi(user: JWTPayload = Depends(require_ketoan_user)) -> JWTPayload:
    """Gate SỬA/XOÁ lệnh thu chi — chỉ CEO/admin/trợ lý CEO."""
    if user.role not in _CEO_THUCHI_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Chỉ CEO được sửa/xoá lệnh thu chi. Kế Toán chỉ được tạo mới — "
            "cần sửa/xoá vui lòng báo CEO.",
        )
    return user
