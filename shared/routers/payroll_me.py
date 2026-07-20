"""Shared router /api/payroll/me — cho phép NV mọi app (baogia/marketing/muahang/
ketoan/saleadmin/ceo/hcns) xem chấm công + lương cá nhân của mình.

Anh Quang 2026-06-06: NV vào Hồ Sơ Cá Nhân ở app của mình (không link sang HCNS).
Reuse logic /api/payroll/me của HCNS bằng cách import + delegate.
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from shared.auth import JWTPayload, current_user
from shared.db import get_db

router = APIRouter()


@router.get("/me")
def shared_my_payroll(
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    thang: Optional[str] = None,
):
    """Delegate sang hcns.payroll.my_payroll — share cùng logic, cùng DB.

    Auth chỉ cần login (current_user) — endpoint chỉ trả data của user.username.
    """
    try:
        from hcns.app.routers.payroll import my_payroll as _hcns_my_payroll
    except Exception as e:
        raise HTTPException(500, f"Cannot import hcns.payroll: {e}")
    return _hcns_my_payroll(user=user, db=db, thang=thang)
