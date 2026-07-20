"""Chat Internal Service — Container chung cho TẤT CẢ 7 app (port 8011).

Anh Quang 2026-06-13: Refactor — gom 4 chat container cũ (baogia_chat,
marketing_chat, muahang_chat, saleadmin_chat) thành 1 container duy nhất
phục vụ chat web inter-app + notifications cho 7 app.

Endpoints:
- /api/chat/*                      — Chat web inter-app (chung shared rooms/messages)
- /api/notifications/baogia/*      — Notifications baogia (filter source_app)
- /api/notifications/marketing/*   — Notifications marketing
- /api/notifications/muahang/*     — Notifications muahang
- /api/notifications/hcns/*        — Notifications hcns
- /api/notifications/ketoan/*      — Notifications ketoan
- /api/notifications/ceo/*         — Notifications ceo
- /api/notifications/saleadmin/*   — Notifications saleadmin
- /health                          — Service health check

nginx rewrite: `<app>.qlpps.com/api/notifications/...` → này container
`/api/notifications/<app>/...` (proxy_pass with URI prefix tự cắt).
"""
from fastapi import FastAPI

from shared.config import settings
from shared.middleware import register_error_handlers, install_sliding_session
from shared.services.notifications_router import make_router as make_notifications_router

from hcns.app.routers.chat import router as chat_router


# Eager-import models để tránh SQLAlchemy mapper init race khi serve cross-app
import baogia.app.models  # noqa: F401
import marketing.app.models  # noqa: F401
import muahang.app.models  # noqa: F401
import hcns.app.models  # noqa: F401
import ketoan.app.models  # noqa: F401
import saleadmin.app.models  # noqa: F401


app = FastAPI(
    title="QLPPS Chat Internal",
    version="0.1.0",
)

register_error_handlers(app)
install_sliding_session(app)


# Chat web inter-app — chung shared.chat_rooms + shared.chat_messages
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])


# Notifications mount per-app với prefix khác nhau.
# nginx rewrite Host → prefix: baogia.qlpps.com/api/notifications/count-unread
# → chat_internal/api/notifications/baogia/count-unread
for _app_name in ("baogia", "marketing", "muahang", "hcns", "ketoan", "ceo", "saleadmin"):
    app.include_router(
        make_notifications_router(_app_name),
        prefix=f"/api/notifications/{_app_name}",
        tags=[f"notif:{_app_name}"],
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "chat_internal",
        "env": settings.app_env,
    }
