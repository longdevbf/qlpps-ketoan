"""SSE (Server-Sent Events) helper cho FastAPI.

Dùng trong CEO app để push realtime event xuống browser:
    from shared.sse import sse_stream
    from shared.events import subscribe

    @router.get("/sse/events")
    async def stream(user = Depends(require_ceo())):
        return sse_stream(subscribe("revenue:*", "approval:*", "feedback:*"))

Format SSE chuẩn:
    event: revenue:new
    data: {"id": 123, "so_tien": 1000000}

Browser:
    const es = new EventSource("/sse/events");
    es.addEventListener("revenue:new", e => {
        const data = JSON.parse(e.data);
        ...
    });
"""
from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import Request
from fastapi.responses import StreamingResponse


_KEEPALIVE_COMMENT = ": keepalive\n\n"


async def _format_sse(events: AsyncIterator[dict], request: Request) -> AsyncIterator[bytes]:
    """Convert event dict → SSE wire format. Tự huỷ khi client disconnect."""
    try:
        async for evt in events:
            if await request.is_disconnected():
                break
            channel = evt.get("channel", "message")
            if channel == "_heartbeat":
                yield _KEEPALIVE_COMMENT.encode("utf-8")
                continue
            data = json.dumps(evt.get("data", {}), default=str, ensure_ascii=False)
            chunk = f"event: {channel}\ndata: {data}\n\n"
            yield chunk.encode("utf-8")
    except Exception:
        # client đã đóng, hoặc Redis lỗi — kết thúc stream im lặng
        return


def sse_stream(events: AsyncIterator[dict], request: Request) -> StreamingResponse:
    """Wrap async event iterator thành SSE response."""
    return StreamingResponse(
        _format_sse(events, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",      # tắt nginx buffering
            "Connection": "keep-alive",
        },
    )
