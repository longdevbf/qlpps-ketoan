"""Sliding-session middleware — idle timeout cho cookie access_token.

Mỗi request có cookie hợp lệ → kiểm tra TTL còn lại; nếu < 50% thì cấp
token mới với exp = now + JWT_ACCESS_TTL_MIN. User idle quá TTL không
gọi request → token tự hết hạn → 401 → frontend redirect login.

Skip khi response đã set Set-Cookie cho access_token (login / logout /
refresh) để không đè lên phán quyết của handler.

ASGI native — KHÔNG dùng BaseHTTPMiddleware (gây deadlock với
StreamingResponse/SSE và làm `RuntimeError: generator didn't stop after
throw()` lan ra mọi endpoint khác).
"""
from datetime import datetime, timezone

import jwt as pyjwt

from shared.auth import (
    access_ttl_min_for_role,
    create_access_token,
    is_token_force_logged_out,
)
from shared.config import settings


_COOKIE_NAME = "access_token"
_COOKIE_PREFIX = b"access_token="
_RENEW_THRESHOLD = 0.5   # renew when remaining < 50% TTL


def _extract_cookie(headers: list) -> str | None:
    """Lấy giá trị cookie access_token từ list ASGI headers."""
    for k, v in headers:
        if k.lower() == b"cookie":
            for chunk in v.split(b";"):
                chunk = chunk.strip()
                if chunk.startswith(_COOKIE_PREFIX):
                    return chunk[len(_COOKIE_PREFIX):].decode("utf-8", "ignore")
    return None


def _build_renewed_cookie(token: str) -> bytes | None:
    """Decode token, nếu cần renew thì trả về Set-Cookie value mới (bytes).
    Trả None nếu không cần / không hợp lệ.
    """
    try:
        payload = pyjwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_alg],
        )
    except pyjwt.PyJWTError:
        return None
    if payload.get("typ") != "access":
        return None
    # KHÔNG gia hạn token đã bị 'đăng xuất mọi thiết bị' — giữ iat cũ để current_user
    # từ chối (nếu gia hạn, iat mới sẽ vượt mốc force-logout → lách mất). Fail-soft.
    if is_token_force_logged_out(payload.get("username") or "", payload.get("iat") or 0):
        return None
    now = int(datetime.now(tz=timezone.utc).timestamp())
    exp = int(payload.get("exp", 0))
    remaining = exp - now
    # TTL theo role (CEO 30 ngày) để ngưỡng gia hạn + Max-Age cookie nhất quán
    # với lúc issue token; tránh CEO bị rút ngắn phiên khi gia hạn.
    ttl_total = access_ttl_min_for_role(payload.get("role") or "") * 60
    if remaining <= 0 or remaining >= ttl_total * _RENEW_THRESHOLD:
        return None
    try:
        new_token, _ = create_access_token(
            int(payload["sub"]),
            payload["username"],
            payload["role"],
            payload.get("apps") or [],
        )
    except Exception:
        return None
    secure_flag = b"" if settings.is_dev else b"; Secure"
    return (
        f"{_COOKIE_NAME}={new_token}; Max-Age={ttl_total}; "
        f"HttpOnly; Path=/; SameSite=Lax"
    ).encode("ascii") + secure_flag


class SlidingSessionMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        token = _extract_cookie(scope.get("headers") or [])
        if not token:
            await self.app(scope, receive, send)
            return

        async def _send(message):
            if message["type"] != "http.response.start":
                await send(message)
                return
            headers = list(message.get("headers") or [])
            # Skip nếu handler đã set Set-Cookie cho access_token
            already_set = any(
                k.lower() == b"set-cookie" and v.lstrip().lower().startswith(_COOKIE_PREFIX)
                for k, v in headers
            )
            if not already_set:
                renewed = _build_renewed_cookie(token)
                if renewed is not None:
                    headers.append((b"set-cookie", renewed))
                    message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, _send)


def install_sliding_session(app) -> None:
    """Wire sliding-session middleware vào FastAPI app instance."""
    app.add_middleware(SlidingSessionMiddleware)
