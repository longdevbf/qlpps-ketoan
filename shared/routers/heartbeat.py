"""Heartbeat tracker — ghi nhận NV thao tác thật trên frontend.

Anh Quang 2026-06-08: FE bắt sự kiện user interaction (mousedown/keydown/wheel/
touchstart/click), ping mỗi 60s NẾU có interaction. Idle 5 phút → FE ngừng ping.
Backend throttle 30s/NV để không ghi DB quá nhiều.

Endpoint: POST /api/me/heartbeat → cập nhật hcns.employees.last_active_at = NOW()
"""
from __future__ import annotations

import time as _time
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.auth import JWTPayload, current_user
from shared.db import get_db


router = APIRouter()

# In-process cache username → last DB write timestamp (epoch seconds).
# Throttle 30s — bấm liên tục cũng chỉ UPDATE DB 1 lần/30s/NV.
_LAST_WRITE: dict[str, float] = {}
_THROTTLE_SEC = 30.0


@router.post("/me/heartbeat", tags=["heartbeat"])
def heartbeat(
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """FE gọi mỗi 60s khi có thao tác → set last_active_at = NOW().

    Throttle 30s/NV (in-memory) để bấm dồn dập không tạo nhiều UPDATE.
    """
    uname = (user.username or "").lower()
    if not uname:
        return {"ok": False, "reason": "no_username"}

    now = _time.time()
    last = _LAST_WRITE.get(uname, 0.0)
    if now - last < _THROTTLE_SEC:
        return {"ok": True, "throttled": True}

    try:
        db.execute(text(
            "UPDATE hcns.employees SET last_active_at = NOW() "
            "WHERE LOWER(username) = :u"
        ), {"u": uname})
        db.commit()
        _LAST_WRITE[uname] = now
        return {"ok": True, "written": True}
    except Exception as e:
        try: db.rollback()
        except Exception: pass
        return {"ok": False, "error": str(e)[:200]}
