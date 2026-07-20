"""Profile + đổi mật khẩu cho FE Kế Toán.

FE templates/index.html mở modal "Đổi mật khẩu" → PUT /api/profile với
body discriminator action ∈ {update_info, change_password}.

Pattern theo baogia/app/routers/profile.py + marketing/app/routers/extras.py:
verify password (argon2 qua shared.auth.password) + log audit.
"""
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload, require_app
from shared.auth.password import hash_password, verify_password
from shared.db import get_db
from shared.models import User


router = APIRouter()
_REQ = require_app("ketoan")


@router.get("/api/profile")
def get_profile(
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "username": user.username,
        "role": user.role,
        "apps": list(user.apps or []),
        "user_id": user.sub,
    }
    try:
        u = db.query(User).filter(User.id == user.sub).first()
        if u:
            out.update({
                "ho_ten": u.full_name,
                "full_name": u.full_name,
                "email": u.email,
                "phone": u.phone,
                "active": u.active,
            })
    except SQLAlchemyError:
        db.rollback()

    try:
        row = db.execute(text(
            "SELECT phong_ban, chuc_vu FROM hcns.employees "
            "WHERE username = :u AND trang_thai IN ('active', 'Đang làm') LIMIT 1"
        ), {"u": user.username}).first()
        if row:
            out["phong_ban"] = row[0]
            out["chuc_vu"] = row[1]
            cv = (row[1] or "").lower()
            jwt_role = (user.role or "").lower()
            if jwt_role in ("admin", "ceo", "assistant_ceo") or "giám đốc" in cv:
                out["vai_tro"] = "ceo"
            elif jwt_role == "manager" or "quản" in cv or "manager" in cv:
                out["vai_tro"] = "manager"
            elif jwt_role == "leader" or "lead" in cv:
                out["vai_tro"] = "leader"
            else:
                out["vai_tro"] = "nhan_vien"
    except SQLAlchemyError:
        db.rollback()
    except Exception:
        pass

    if "vai_tro" not in out:
        jwt_role = (user.role or "").lower()
        if jwt_role in ("admin", "ceo", "assistant_ceo"):
            out["vai_tro"] = "ceo"
        elif jwt_role == "manager":
            out["vai_tro"] = "manager"
        elif jwt_role == "leader":
            out["vai_tro"] = "leader"
        else:
            out["vai_tro"] = "nhan_vien"

    return out


# ─── PUT /api/profile (update_info | change_password) ───────────────────────

class _ProfileUpdate(BaseModel):
    action: str  # "update_info" | "change_password"
    ho_ten: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    confirm_password: Optional[str] = None


@router.put("/api/profile")
def update_profile(
    body: _ProfileUpdate,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """FE templates/index.html dùng action discriminator: update_info | change_password."""
    u = db.query(User).filter(User.id == user.sub).first()
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy tài khoản")

    if body.action == "update_info":
        new_name = (body.ho_ten or "").strip()
        if not new_name:
            return {"ok": False, "error": "Họ tên không được để trống"}
        if len(new_name) > 128:
            return {"ok": False, "error": "Họ tên tối đa 128 ký tự"}
        old_name = u.full_name
        u.full_name = new_name
        db.commit()
        log_action(
            db, app="ketoan", action="update_profile_info", user=user, request=request,
            resource=f"user:{u.id}",
            payload={"old": old_name, "new": new_name},
        )
        return {"ok": True, "message": "Đã cập nhật thông tin"}

    if body.action == "change_password":
        cur = body.current_password or ""
        new = body.new_password or ""
        confirm = body.confirm_password or ""
        if not cur or not new or not confirm:
            return {"ok": False, "error": "Vui lòng điền đầy đủ thông tin"}
        if new != confirm:
            return {"ok": False, "error": "Mật khẩu mới và xác nhận không khớp"}
        if len(new) < 6:
            return {"ok": False, "error": "Mật khẩu mới phải ít nhất 6 ký tự"}
        if not verify_password(cur, u.password_hash or ""):
            return {"ok": False, "error": "Mật khẩu hiện tại không đúng"}
        u.password_hash = hash_password(new)
        db.commit()
        log_action(
            db, app="ketoan", action="change_password", user=user, request=request,
            resource=f"user:{u.id}",
        )
        return {"ok": True, "message": "Đã đổi mật khẩu"}

    return {"ok": False, "error": f"Action không hỗ trợ: {body.action}"}
