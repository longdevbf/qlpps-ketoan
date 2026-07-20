"""Online presence tracking — shared across all apps.

Bất kỳ request có JWT hợp lệ ở mọi app đều mark user online (chat:online:{u} TTL 60s)
+ ghi last_seen (TTL 30 ngày). Frontend chat dùng presenceMap để hiển thị
"Đang hoạt động" / "X giờ trước".
"""
from __future__ import annotations

import time
from typing import Optional


_redis_client = None


def _get_redis():
    """Lazy singleton — fallback None nếu Redis không kết nối được."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis  # sync client
        from shared.config import settings
        _redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        # Test ping
        _redis_client.ping()
    except Exception:
        _redis_client = None
    return _redis_client


def mark_online(username: Optional[str]) -> None:
    """Mark user online + cập nhật last_seen. Fail-soft.

    Skip nếu chat:logout:{u} blacklist tồn tại (user vừa explicit logout).
    """
    if not username:
        return
    r = _get_redis()
    if r is None:
        return
    try:
        if r.exists(f"chat:logout:{username}"):
            return  # blacklisted — user logout, ko cho mark online
        ts = str(int(time.time()))
        r.setex(f"chat:online:{username}", 1800, ts)
        r.setex(f"chat:last_seen:{username}", 60 * 60 * 24 * 30, ts)
    except Exception:
        pass


def mark_offline(username: Optional[str]) -> None:
    """Xoá online status + set blacklist 30p (chống tab khác mark online lại).

    Gọi khi user click "Đăng xuất" explicit.
    """
    if not username:
        return
    r = _get_redis()
    if r is None:
        return
    try:
        r.delete(f"chat:online:{username}")
        r.setex(f"chat:logout:{username}", 1800, "1")  # blacklist 30 phút
        ts = str(int(time.time()))
        r.setex(f"chat:last_seen:{username}", 60 * 60 * 24 * 30, ts)
        # Reset cả sse_count → tab khác (nếu còn) khi SSE drop sẽ KHÔNG decrement nữa
        r.delete(f"chat:sse_count:{username}")
    except Exception:
        pass


def clear_logout_blacklist(username: Optional[str]) -> None:
    """Xoá blacklist khi user re-login (cho phép mark_online hoạt động lại)."""
    if not username:
        return
    r = _get_redis()
    if r is None:
        return
    try:
        r.delete(f"chat:logout:{username}")
    except Exception:
        pass


def sse_connect(username: Optional[str]) -> int:
    """Track 1 SSE connection mới — INCR sse_count + mark online.

    Return: số connection active hiện tại (>=1).
    """
    if not username:
        return 0
    r = _get_redis()
    if r is None:
        return 0
    try:
        if r.exists(f"chat:logout:{username}"):
            return 0  # blacklisted
        count = r.incr(f"chat:sse_count:{username}")
        # TTL cho sse_count để fallback (vd server crash) — 1h
        r.expire(f"chat:sse_count:{username}", 3600)
        # Mark online
        ts = str(int(time.time()))
        r.setex(f"chat:online:{username}", 1800, ts)
        r.setex(f"chat:last_seen:{username}", 60 * 60 * 24 * 30, ts)
        return int(count or 0)
    except Exception:
        return 0


def sse_disconnect(username: Optional[str]) -> int:
    """1 SSE connection đóng — DECR sse_count.

    Nếu count == 0 → user đóng hết tab → mark offline ngay (DEL chat:online).
    KHÔNG set blacklist (vì user có thể chỉ reload tab → SSE reconnect ngay).
    Return: số connection còn lại.
    """
    if not username:
        return 0
    r = _get_redis()
    if r is None:
        return 0
    try:
        count = r.decr(f"chat:sse_count:{username}")
        count = int(count or 0)
        if count < 0:
            r.set(f"chat:sse_count:{username}", 0)
            count = 0
        if count <= 0:
            # Tab cuối đóng → offline ngay
            r.delete(f"chat:online:{username}")
            ts = str(int(time.time()))
            r.setex(f"chat:last_seen:{username}", 60 * 60 * 24 * 30, ts)
            r.delete(f"chat:sse_count:{username}")
        return count
    except Exception:
        return 0
