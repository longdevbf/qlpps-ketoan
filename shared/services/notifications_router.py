"""Notifications router dùng chung — mount vào MỖI app (baogia/marketing/muahang).

Mỗi app mount với app_name của riêng nó → noti hiện chỉ noti CỦA app đó.

    from shared.services.notifications_router import make_router
    app.include_router(
        make_router("baogia"),
        prefix="/api/notifications", tags=["notifications"],
    )

Backward-compat: `router` (alias) = make_router(None) → trả MỌI noti
(behavior cũ). Khuyến nghị tất cả app pass app_name explicit.

Endpoints (tất cả filter theo source_app nếu app_name set):
    GET    /                  — list noti unread của user
    GET    /count-unread      — { count, target, source_app }
    POST   /{id}/mark-read
    POST   /mark-all-read
    DELETE /{id}
    GET    /sse               — Server-Sent Events realtime push
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Annotated, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from pydantic import BaseModel

try:
    import redis as _redis_mod  # type: ignore
except Exception:  # pragma: no cover
    _redis_mod = None  # type: ignore

from shared.auth import JWTPayload, current_user
from shared.config import settings
from shared.db import get_db
from shared.events import subscribe
from shared.models import Notification, PushSubscription
from shared.sse import sse_stream


_USER = Depends(current_user)
_ADMIN_ROLES = {"admin", "ceo", "assistant_ceo"}


# ── Redis cache helper (fail-soft) ──────────────────────────────────────────
_redis = None
_redis_init = False


def _get_redis():
    """Lazy singleton Redis client. Trả None nếu lib chưa cài hoặc kết nối lỗi."""
    global _redis, _redis_init
    if _redis_init:
        return _redis
    _redis_init = True
    if _redis_mod is None:
        _redis = None
        return None
    try:
        _redis = _redis_mod.Redis.from_url(
            os.getenv("REDIS_URL", "redis://redis:6379/0"),
            socket_timeout=2,
            socket_connect_timeout=2,
            decode_responses=True,
        )
    except Exception:
        _redis = None
    return _redis


def cache_get_or_set(key: str, ttl: int, compute_fn: Callable):
    """Get JSON từ Redis, miss thì compute + setex. Redis lỗi → fallback compute."""
    r = _get_redis()
    if r is not None:
        try:
            raw = r.get(key)
            if raw is not None:
                return json.loads(raw)
        except Exception:
            pass
    value = compute_fn()
    if r is not None:
        try:
            r.setex(key, ttl, json.dumps(value, default=str))
        except Exception:
            pass
    return value


def cache_delete(key: str) -> None:
    """Xoá key khỏi Redis cache. Fail-soft."""
    r = _get_redis()
    if r is None:
        return
    try:
        r.delete(key)
    except Exception:
        pass


def _is_admin(user: JWTPayload) -> bool:
    return user.role in _ADMIN_ROLES


def _resolve_target(user: JWTPayload, username: Optional[str]) -> str:
    if username and _is_admin(user):
        return username
    return user.username


class _PushSubBody(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    user_agent: Optional[str] = None
    source_app: Optional[str] = None


def _serialize(n: Notification) -> dict:
    return {
        "id": n.id,
        "target_username": n.target_username,
        "source_app": n.source_app,
        "event_type": n.event_type,
        "title": n.title,
        "message": n.message,
        "ref_type": n.ref_type,
        "ref_id": n.ref_id,
        "url": n.url,
        "severity": n.severity,
        "seen": bool(n.seen),
        "seen_at": n.seen_at.isoformat() if n.seen_at else None,
        "created_by": n.created_by,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


def make_router(app_name: Optional[str] = None) -> APIRouter:
    """Tạo router scoped theo app_name. Nếu None → trả mọi noti (legacy)."""

    router = APIRouter()

    # ── Cross-app dedupe helper ────────────────────────────────────────────
    # notify_lead_both tạo 2 rows (marketing + baogia) cho cùng lead:chuyen_kd
    # → chuông ở BẤT KỲ subdomain nào cũng phải hiển thị/đếm như 1 event.
    # Sub-query: chỉ lấy MAX(id) trong mỗi nhóm (event_type, ref_type, ref_id)
    # với các noti có ref (lead:*, ticket:*, …); noti không có ref (system,
    # generic) coi mỗi row là unique.
    def _dedup_ids_subq(target: str, only_unread: bool):
        """Return sub-query select id — dedupe theo (event_type, ref_type, ref_id).
        Rows có ref: pick MAX(id) mỗi group. Rows không ref: pick tất cả.
        """
        from sqlalchemy import func as _f, or_, and_
        base = select(Notification.id).where(Notification.target_username == target)
        if only_unread:
            base = base.where(Notification.seen.is_(False))
        # Rows KHÔNG có ref → pass-through
        no_ref = base.where(
            or_(Notification.ref_id.is_(None), Notification.ref_type.is_(None))
        )
        # Rows CÓ ref → chỉ pick MAX(id) mỗi (event_type, ref_type, ref_id)
        group_q = (
            select(_f.max(Notification.id).label("mid"))
            .where(Notification.target_username == target)
            .where(Notification.ref_id.isnot(None))
            .where(Notification.ref_type.isnot(None))
        )
        if only_unread:
            group_q = group_q.where(Notification.seen.is_(False))
        group_q = group_q.group_by(
            Notification.event_type, Notification.ref_type, Notification.ref_id,
        )
        return no_ref.union(select(group_q.subquery().c.mid))

    @router.get("")
    @router.get("/")
    def list_notifications(
        user: Annotated[JWTPayload, _USER],
        db: Annotated[Session, Depends(get_db)],
        all: bool = Query(default=False, description="true = cả seen, mặc định chỉ unread"),
        username: Optional[str] = Query(default=None, description="admin only — xem của user khác"),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ):
        target = _resolve_target(user, username)
        # Cross-app dedupe: bỏ filter source_app, gộp duplicate rows theo ref
        ids_subq = _dedup_ids_subq(target, only_unread=not all).subquery()
        q = (
            select(Notification)
            .where(Notification.id.in_(select(ids_subq.c.id)))
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit).offset(offset)
        )
        rows = db.execute(q).scalars().all()
        return [_serialize(r) for r in rows]

    @router.get("/count-unread")
    def count_unread(
        user: Annotated[JWTPayload, _USER],
        db: Annotated[Session, Depends(get_db)],
        username: Optional[str] = Query(default=None),
    ):
        target = _resolve_target(user, username)

        def _compute():
            from sqlalchemy import func as _f
            # Cross-app dedupe: đếm distinct events (không phân biệt subdomain)
            ids_subq = _dedup_ids_subq(target, only_unread=True).subquery()
            n = db.execute(select(_f.count()).select_from(ids_subq)).scalar() or 0
            return {"count": int(n), "target": target, "source_app": app_name}

        # Cache 5s per user (giảm từ 10s để badge phản ứng nhanh với noti mới)
        cache_key = f"bg:notif:cnt:{target}"
        return cache_get_or_set(cache_key, 5, _compute)

    def _invalidate_count_cache(target: str) -> None:
        """Xoá cache count-unread để lần next fetch trả về số mới nhất."""
        try:
            cache_delete(f"bg:notif:cnt:{target}")
        except Exception:
            pass

    @router.post("/{notif_id}/mark-read")
    def mark_read(
        notif_id: int,
        user: Annotated[JWTPayload, _USER],
        db: Annotated[Session, Depends(get_db)],
    ):
        n = db.get(Notification, notif_id)
        if not n:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification không tồn tại")
        if n.target_username != user.username and not _is_admin(user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền")
        # Cascade mark-read: các noti cùng (target, event_type, ref_type, ref_id)
        # → dedupe seen state cross-app. Nếu noti KHÔNG có ref → chỉ mark 1 row.
        now = datetime.now(timezone.utc)
        if n.ref_id and n.ref_type:
            q = (
                update(Notification)
                .where(Notification.target_username == n.target_username)
                .where(Notification.event_type == n.event_type)
                .where(Notification.ref_type == n.ref_type)
                .where(Notification.ref_id == n.ref_id)
                .where(Notification.seen.is_(False))
                .values(seen=True, seen_at=now)
            )
            res = db.execute(q)
            db.commit()
            _invalidate_count_cache(n.target_username)
            return {"ok": True, "id": n.id, "cascade_updated": res.rowcount}
        # Fallback: 1 row
        if not n.seen:
            n.seen = True
            n.seen_at = now
            db.commit()
            _invalidate_count_cache(n.target_username)
        return {"ok": True, "id": n.id}

    @router.post("/mark-all-read")
    def mark_all_read(
        user: Annotated[JWTPayload, _USER],
        db: Annotated[Session, Depends(get_db)],
    ):
        now = datetime.now(timezone.utc)
        # Cross-app: mark hết noti của user (bỏ filter source_app)
        q = (
            update(Notification)
            .where(Notification.target_username == user.username)
            .where(Notification.seen.is_(False))
            .values(seen=True, seen_at=now)
        )
        res = db.execute(q)
        db.commit()
        _invalidate_count_cache(user.username)
        return {"ok": True, "updated": res.rowcount}

    @router.delete("/{notif_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_notification(
        notif_id: int,
        user: Annotated[JWTPayload, _USER],
        db: Annotated[Session, Depends(get_db)],
    ):
        n = db.get(Notification, notif_id)
        if not n:
            return
        if n.target_username != user.username and not _is_admin(user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền")
        # Cascade delete cross-app (cùng ref) — giữ dữ liệu sạch
        if n.ref_id and n.ref_type:
            target_un = n.target_username
            event_t = n.event_type
            ref_t = n.ref_type
            ref_i = n.ref_id
            db.execute(
                delete(Notification)
                .where(Notification.target_username == target_un)
                .where(Notification.event_type == event_t)
                .where(Notification.ref_type == ref_t)
                .where(Notification.ref_id == ref_i)
            )
        else:
            db.delete(n)
        db.commit()
        _invalidate_count_cache(user.username)

    @router.get("/sse")
    async def notifications_sse(
        request: Request,
        user: Annotated[JWTPayload, _USER],
    ):
        """Realtime push noti cho user qua SSE — cross-app dedupe.

        BỎ filter theo source_app: user ở subdomain nào cũng nhận SSE push
        cho MỌI noti của mình. Cross-app dedupe by (event_type, ref_type, ref_id)
        để tránh 2 events cùng nội dung push liên tiếp — chỉ push cái đầu.
        """
        channel = f"notif:{user.username}"
        _seen_refs: set = set()  # (event_type, ref_type, ref_id) đã push trong session

        async def _events():
            async for evt in subscribe(channel):
                # Heartbeat giữ connection sống
                if evt.get("channel") == "_heartbeat":
                    yield evt
                    continue
                data = evt.get("data", {}) or {}
                # Cross-app dedupe: nếu cùng ref đã push → skip (row baogia + marketing)
                ref_key = (
                    data.get("event_type") or "",
                    data.get("ref_type") or "",
                    data.get("ref_id") or "",
                )
                if all(ref_key) and ref_key in _seen_refs:
                    continue
                if all(ref_key):
                    _seen_refs.add(ref_key)
                yield {
                    "channel": "notification",
                    "data": data,
                }

        return sse_stream(_events(), request=request)

    # ─── Web Push (OS-level notification + badge) ──────────────────────────────
    @router.get("/push/vapid-public-key")
    def push_vapid_public_key():
        """Trả VAPID public key cho FE. Không yêu cầu auth — public info."""
        if not settings.vapid_public_key:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "VAPID chưa được cấu hình ở server",
            )
        return {"publicKey": settings.vapid_public_key}

    @router.post("/push/subscribe")
    def push_subscribe(
        body: _PushSubBody,
        user: Annotated[JWTPayload, _USER],
        db: Annotated[Session, Depends(get_db)],
    ):
        """Upsert subscription theo `endpoint` (unique). Idempotent."""
        if not body.endpoint or not body.p256dh or not body.auth:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Thiếu endpoint/keys")
        existing = db.execute(
            select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        # source_app: ưu tiên app_name của router (server-side truth) > body
        resolved_source = app_name or (body.source_app or "")
        if existing:
            existing.username = user.username
            existing.p256dh = body.p256dh
            existing.auth = body.auth
            existing.user_agent = (body.user_agent or "")[:512] or existing.user_agent
            existing.source_app = (resolved_source or "")[:16] or existing.source_app
            existing.last_seen_at = now
        else:
            db.add(PushSubscription(
                username=user.username,
                endpoint=body.endpoint,
                p256dh=body.p256dh,
                auth=body.auth,
                user_agent=(body.user_agent or "")[:512] or None,
                source_app=(resolved_source or "")[:16] or None,
                last_seen_at=now,
            ))
        db.commit()
        return {"ok": True}

    @router.post("/push/unsubscribe")
    def push_unsubscribe(
        body: _PushSubBody,
        user: Annotated[JWTPayload, _USER],
        db: Annotated[Session, Depends(get_db)],
    ):
        """Xoá subscription theo endpoint. Trả ok kể cả không có để idempotent."""
        if not body.endpoint:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Thiếu endpoint")
        db.execute(
            delete(PushSubscription)
            .where(PushSubscription.endpoint == body.endpoint)
            .where(PushSubscription.username == user.username)
        )
        db.commit()
        return {"ok": True}

    return router


# Backward-compat: legacy `router` không filter theo app. Khuyến cáo dùng
# make_router(app_name) cho noti scoped đúng app.
router = make_router(None)
