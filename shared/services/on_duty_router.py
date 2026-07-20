"""On-duty toggle — KD/manager bật/tắt 'đang trực' để MKT giao lead.

Mount vào MỖI app cần (baogia/marketing):
    from shared.services.on_duty_router import router as on_duty_router
    app.include_router(on_duty_router, tags=["on-duty"])

Endpoints:
    GET  /api/users/me/on-duty      → {is_on_duty: bool}
    PUT  /api/users/me/on-duty      body {is_on_duty: bool} → {ok, is_on_duty}
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.auth import JWTPayload, current_user
from shared.db import get_db
from shared.models import User


router = APIRouter()


# Roles được phép toggle (KD bán lẻ + manager + leader). Role khác (admin/ceo)
# vẫn được toggle nhưng UI baogia chỉ hiện nút cho các role này. Backend cho
# phép tất cả role để future flexibility — không restrict.

class _OnDutyBody(BaseModel):
    is_on_duty: bool


@router.get("/api/users/me/on-duty")
def get_my_on_duty(
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    u = db.execute(
        select(User).where(User.id == user.sub)
    ).scalar_one_or_none()
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User không tồn tại")
    return {
        "username": u.username,
        "is_on_duty": bool(u.is_on_duty),
    }


@router.put("/api/users/me/on-duty")
def set_my_on_duty(
    body: _OnDutyBody,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    u = db.execute(
        select(User).where(User.id == user.sub)
    ).scalar_one_or_none()
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User không tồn tại")
    u.is_on_duty = bool(body.is_on_duty)
    db.commit()
    return {
        "ok": True,
        "username": u.username,
        "is_on_duty": bool(u.is_on_duty),
    }
