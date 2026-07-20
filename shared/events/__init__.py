"""Cross-app event bus qua Redis pub/sub.

Mọi app ghi data quan trọng → emit_event(channel, payload) → CEO + app khác
nghe qua subscribe(). Realtime, không persist.

Usage (publish):
    from shared.events import emit_event
    emit_event("revenue:new", {"id": dt.id, "so_tien": dt.so_tien})

Usage (subscribe — async):
    from shared.events import subscribe
    async for evt in subscribe("revenue:*", "order:*"):
        ...

Channels chuẩn:
    revenue:new        order:new           order:status
    lead:new           lead:status
    quote:new          quote:duyet         quote:reject
    approval:new       approval:done
    feedback:new       opportunity:new
    vc:new             vc:status
    hr:checkin         hr:checkout
    employee:new       employee:status
"""
from .bus import emit_event, subscribe, get_redis

__all__ = ["emit_event", "subscribe", "get_redis"]
