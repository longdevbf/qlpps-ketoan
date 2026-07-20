"""Chat Zalo Service — Container chung cho baogia + marketing (port 8012).

Anh Quang 2026-06-13: Chat Zalo (Pancake) chỉ phục vụ baogia + marketing
— 2 phòng ban có nghiệp vụ chăm sóc khách Zalo. Tách thành 1 container
chung thay vì duplicate trong từng app chat container.

Endpoints:
- /api/chat-zalo/*                 — Pancake conversations / messages / send
- /health                          — Service health check

nginx route: baogia.qlpps.com + marketing.qlpps.com → /api/chat-zalo/* qua
container này.
"""
from fastapi import FastAPI

from shared.config import settings
from shared.middleware import register_error_handlers, install_sliding_session

from baogia.app.routers.chat_zalo import router as chat_zalo_router


# Eager-import models để tránh SQLAlchemy mapper init race
import baogia.app.models  # noqa: F401
import marketing.app.models  # noqa: F401


app = FastAPI(
    title="QLPPS Chat Zalo",
    version="0.1.0",
)

register_error_handlers(app)
install_sliding_session(app)


# Chat Zalo (Pancake) — router đã có prefix `/api/chat-zalo` bên trong
app.include_router(chat_zalo_router, tags=["chat_zalo"])


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "chat_zalo",
        "env": settings.app_env,
    }
