"""JWT issue + verify + FastAPI dependency.

Usage trong app downstream (baogia/marketing/muahang):
    from fastapi import Depends
    from shared.auth import current_user, JWTPayload, require_app

    @router.get("/api/quotes")
    def list_quotes(user: JWTPayload = Depends(require_app("baogia"))):
        ...
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional, TYPE_CHECKING
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, field_validator

from shared.config import settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


_bearer = HTTPBearer(auto_error=False)


class JWTPayload(BaseModel):
    sub: int          # user_id (encoded in JWT as str per RFC 7519)
    username: str
    role: str
    apps: list[str]
    jti: str
    exp: int
    iat: int
    typ: str = "access"  # access | refresh

    @field_validator("sub", mode="before")
    @classmethod
    def _coerce_sub(cls, v):
        return int(v) if isinstance(v, str) else v


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


# Anh Quang 2026-06-20: CEO không muốn bị tự đăng xuất giữa chừng → phiên
# đăng nhập dài (mặc định 30 ngày). User thường vẫn giữ TTL ngắn theo
# JWT_ACCESS_TTL_MIN. Vì hệ thống dùng SSO (1 token dùng chung mọi app),
# phân biệt theo role chứ không theo app.
_LONG_SESSION_ROLES = frozenset({"ceo"})


def access_ttl_min_for_role(role: str) -> int:
    """TTL (phút) của access token theo role.

    role ∈ _LONG_SESSION_ROLES → jwt_access_ttl_min_ceo (mặc định 30 ngày);
    còn lại → jwt_access_ttl_min (global). Dùng chung cho lúc issue token
    (auth login/refresh) lẫn lúc gia hạn (sliding-session) để TTL nhất quán.
    """
    if role in _LONG_SESSION_ROLES:
        return settings.jwt_access_ttl_min_ceo
    return settings.jwt_access_ttl_min


def create_access_token(user_id: int, username: str, role: str, apps: list[str]) -> tuple[str, str]:
    """Returns (token, jti)."""
    jti = str(uuid4())
    now = _now_utc()
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "apps": apps,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=access_ttl_min_for_role(role))).timestamp()),
        "typ": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_alg)
    return token, jti


def create_refresh_token(user_id: int, username: str, role: str, apps: list[str]) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at)."""
    jti = str(uuid4())
    now = _now_utc()
    expires_at = now + timedelta(days=settings.jwt_refresh_ttl_days)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "apps": apps,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "typ": "refresh",
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_alg)
    return token, jti, expires_at


def decode_token(token: str) -> JWTPayload:
    """Decode + verify signature + expiry. Raise jwt.PyJWTError nếu invalid."""
    raw = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_alg])
    return JWTPayload(**raw)


def verify_jwt(token: str) -> JWTPayload:
    """Verify token, raise HTTPException 401 nếu invalid."""
    try:
        return decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}")


def _extract_token(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """Lấy token từ Authorization header HOẶC cookie 'access_token' (cross-app SSO)."""
    if creds and creds.scheme.lower() == "bearer":
        return creds.credentials
    cookie = request.cookies.get("access_token")
    if cookie:
        return cookie
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing auth token")


def current_user(token: Annotated[str, Depends(_extract_token)]) -> JWTPayload:
    payload = verify_jwt(token)
    if payload.typ != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token cannot be used as access")

    # Anh Quang 2026-06-13: Active check — NV nghỉ việc (HCNS đánh dấu
    # `trang_thai='Đã nghỉ'` → `shared.users.active=false`) PHẢI bị kick
    # khỏi hệ thống ngay cả khi JWT còn hạn. Cache kết quả Redis 60s để
    # tránh query DB mỗi request. Fail-soft: Redis/DB lỗi → không block.
    try:
        _check_user_active_or_401(payload.username)
    except HTTPException:
        raise
    except Exception:
        pass  # Fail-soft

    # ── Đăng xuất mọi thiết bị ── token cấp TRƯỚC mốc force-logout → 401 (buộc login lại).
    # Fail-soft: is_token_force_logged_out tự trả False nếu Redis lỗi → không chặn nhầm.
    if is_token_force_logged_out(payload.username, payload.iat):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Bạn đã được đăng xuất khỏi thiết bị này. Vui lòng đăng nhập lại.",
        )

    # ── Presence tracking ── mọi request có JWT hợp lệ ở mọi app đều mark online
    try:
        from shared.utils.presence import mark_online
        mark_online(payload.username)
    except Exception:
        pass
    return payload


def _check_user_active_or_401(username: str) -> None:
    """Raise 401 nếu user inactive (đã nghỉ việc).

    Cache Redis TTL 60s. Khi HCNS đánh dấu Đã nghỉ → set_user_active() đồng
    thời invalidate Redis key này → NV bị kick TRONG VÒNG 60s (worst case).
    """
    import os
    import redis as _redis_mod
    cache_key = f"user:active:{username}"
    try:
        url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        r = _redis_mod.Redis.from_url(
            url, socket_timeout=2, socket_connect_timeout=2, decode_responses=True,
        )
        cached = r.get(cache_key)
    except Exception:
        cached = None
        r = None

    if cached == "1":
        return
    if cached == "0":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Tài khoản đã bị vô hiệu hóa. Liên hệ HCNS nếu có thắc mắc.",
        )

    # Cache miss → query DB
    try:
        from shared.db import SessionLocal
        from sqlalchemy import text as _sa_text
        with SessionLocal() as db:
            row = db.execute(
                _sa_text("SELECT active FROM shared.users WHERE username = :u"),
                {"u": username},
            ).first()
            is_active = bool(row[0]) if row else False
        if r is not None:
            try:
                r.setex(cache_key, 60, "1" if is_active else "0")
            except Exception:
                pass
        if not is_active:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Tài khoản đã bị vô hiệu hóa. Liên hệ HCNS nếu có thắc mắc.",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # Fail-soft


def _force_logout_redis():
    """Redis client cho cờ force-logout. None nếu lỗi (fail-soft)."""
    import os
    import redis as _redis_mod
    url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return _redis_mod.Redis.from_url(
        url, socket_timeout=2, socket_connect_timeout=2, decode_responses=True,
    )


def is_token_force_logged_out(username: str, iat: int) -> bool:
    """True nếu access token (iat) được cấp TRƯỚC mốc 'đăng xuất mọi thiết bị'
    của user (Redis auth:logout_after:{username}). Fail-soft: Redis lỗi → False."""
    try:
        val = _force_logout_redis().get(f"auth:logout_after:{username}")
    except Exception:
        return False
    if not val:
        return False
    try:
        return int(iat) < int(float(val))
    except (TypeError, ValueError):
        return False


def force_logout_all(username: str) -> bool:
    """ĐĂNG XUẤT user khỏi MỌI thiết bị: mọi access token cấp TRƯỚC thời điểm này
    đều bị vô hiệu (current_user trả 401 + sliding-session không gia hạn) → user
    phải đăng nhập lại. Cờ TTL 32 ngày (> max access TTL 30 ngày). True nếu set OK."""
    try:
        import time
        _force_logout_redis().setex(
            f"auth:logout_after:{username}", 32 * 24 * 3600, str(int(time.time())),
        )
        return True
    except Exception:
        return False


def clear_force_logout(username: str) -> bool:
    """Gỡ cờ force-logout của user (nếu cần khôi phục sớm)."""
    try:
        _force_logout_redis().delete(f"auth:logout_after:{username}")
        return True
    except Exception:
        return False


def require_role(*allowed_roles: str):
    """Factory dependency — chỉ cho roles được phép."""
    def _checker(user: JWTPayload = Depends(current_user)) -> JWTPayload:
        if user.role not in allowed_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Role {user.role} không có quyền")
        return user
    return _checker


# Role chuyên trách → app mặc định. Role này luôn được phép truy cập app
# tương ứng kể cả khi `apps` claim trong JWT cũ thiếu (data migrate sót,
# admin tạo user manual không tick app...). Đồng bộ với `shared.services.role_map`.
_ROLE_TO_APP: dict[str, str] = {
    "kd":  "baogia",
    "mkt": "marketing",
    "mh":  "muahang",
    "kt":  "ketoan",
    "sa":  "saleadmin",
    "hr":  "hcns",
}


def require_app(app_name: str, leader_dept: Optional[str] = None):
    """Factory dependency — chỉ cho user có app trong `apps` claim.

    `leader_dept`: nếu set, role="leader" + `hcns.employees.phong_ban == leader_dept`
    cũng được bypass app check. Dùng khi 1 phòng có leader cần xem toàn dữ liệu
    của app phòng đó (vd: leader phòng Mua Hàng → app `muahang`).
    """
    def _checker(
        user: JWTPayload = Depends(current_user),
        db: Optional["Session"] = Depends(_optional_db),
    ) -> JWTPayload:
        # Admin / CEO / Assistant CEO bypass app check (đọc xuyên suốt 6 PB)
        if user.role in ("admin", "ceo", "assistant_ceo"):
            return user
        if app_name in (user.apps or []):
            return user
        # Anh Quang 2026-06-25: ĐÃ GỠ mọi fallback phân quyền theo PHÒNG BAN/ROLE
        # trong code (KD→baogia+marketing, Công Nghệ→4 app, role chuyên trách,
        # leader phòng). Quyền app giờ CHỈ theo `apps` claim — do HCNS quản lý
        # (shared.users.apps). `db`/`leader_dept` giữ ở chữ ký cho tương thích.
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"User không có quyền truy cập app {app_name}",
        )
    return _checker


def _optional_db():
    """Inject Session khi có shared.db.get_db; nếu chưa wire thì trả None.

    Gặp khi require_app dùng ở context không cần DB (vd test isolation).

    LƯU Ý: KHÔNG bọc `yield db` trong outer `try/except Exception` — vì khi
    endpoint throw exception, FastAPI dependency cleanup gọi gen.athrow() vào
    `yield`. Nếu outer except Exception catch được → generator yield thêm
    `None` thay vì stop → RuntimeError("generator didn't stop after throw()").
    Cleanup này lan ra mọi endpoint downstream (lỗi 500 ngẫu nhiên).
    """
    # Chỉ catch ImportError khi shared.db chưa wire (test isolation)
    try:
        from shared.db import get_db
    except ImportError:
        yield None
        return

    gen = get_db()
    try:
        db = next(gen)
    except StopIteration:
        yield None
        return

    try:
        yield db
    finally:
        # Drain generator để get_db chạy finally (db.close())
        try:
            next(gen)
        except StopIteration:
            pass


def require_ceo(write: bool = False):
    """Dependency dành riêng cho CEO app.

    write=False → cả ceo + assistant_ceo (read-only) đều vào.
    write=True  → chỉ ceo + admin (assistant_ceo không phê duyệt được).
    """
    def _checker(user: JWTPayload = Depends(current_user)) -> JWTPayload:
        if write:
            allowed = ("ceo", "admin")
        else:
            allowed = ("ceo", "admin", "assistant_ceo")
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ CEO mới có quyền truy cập")
        return user
    return _checker
