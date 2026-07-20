"""Redis pub/sub event bus implementation.

Publisher: sync — gọi từ business logic sau khi commit DB.
Subscriber: async — dùng trong SSE stream của CEO app.

Channel naming: "events:<topic>:<sub>" — VD events:revenue:new, events:approval:done.
Payload: JSON str. Chỉ chứa id + tóm tắt; consumer query DB nếu cần đầy đủ.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

import redis as redis_sync
import redis.asyncio as redis_async

from shared.config import settings


_log = logging.getLogger("shared.events")
_CHANNEL_PREFIX = "events:"

# 1 sync client cho publisher (lifecycle = process)
_sync_client: Optional[redis_sync.Redis] = None


def get_redis() -> redis_sync.Redis:
    """Lazy singleton sync Redis client cho publisher."""
    global _sync_client
    if _sync_client is None:
        _sync_client = redis_sync.from_url(settings.redis_url, decode_responses=True)
    return _sync_client


def emit_event(channel: str, payload: dict[str, Any]) -> int:
    """Publish 1 event lên Redis. Trả về số subscriber nhận được.

    Không raise khi Redis down — chỉ log warning, tránh chặn business flow.
    """
    full_channel = f"{_CHANNEL_PREFIX}{channel}"
    body = {
        "channel": channel,
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "data": payload,
    }
    try:
        client = get_redis()
        return client.publish(full_channel, json.dumps(body, default=str, ensure_ascii=False))
    except Exception as e:
        _log.warning("emit_event %s failed: %s", channel, e)
        return 0


async def subscribe(*patterns: str) -> AsyncIterator[dict[str, Any]]:
    """Async generator yield từng event match pattern.

    Patterns hỗ trợ wildcard Redis:
        subscribe("revenue:*")            -- mọi event revenue
        subscribe("approval:*", "feedback:*")
        subscribe("*")                     -- mọi event

    Yield: dict {channel, ts, data}
    """
    client = redis_async.from_url(settings.redis_url, decode_responses=True)
    pubsub = client.pubsub()
    full_patterns = [f"{_CHANNEL_PREFIX}{p}" for p in patterns] or [f"{_CHANNEL_PREFIX}*"]
    await pubsub.psubscribe(*full_patterns)
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
            if msg is None:
                # heartbeat — yield None cho SSE giữ connection sống
                yield {"channel": "_heartbeat", "ts": datetime.now(tz=timezone.utc).isoformat(), "data": {}}
                continue
            if msg.get("type") not in ("message", "pmessage"):
                continue
            try:
                yield json.loads(msg["data"])
            except (json.JSONDecodeError, KeyError) as e:
                _log.warning("subscribe parse err: %s", e)
    except asyncio.CancelledError:
        raise
    finally:
        try:
            await pubsub.punsubscribe(*full_patterns)
            await pubsub.aclose()
            await client.aclose()
        except Exception:
            pass
