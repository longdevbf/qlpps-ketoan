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

# Module DÙNG CHUNG gom về container này (anh Quang 2026-08-20): sửa 1 nơi, 8 app chạy.
from shared.routers.xin_nghi import router as xin_nghi_router
from shared.routers.duyet_chi import router as duyet_chi_router
from shared.routers.giao_viec import router as giao_viec_router
from shared.routers.calendar import router as calendar_router
from shared.routers.payroll_me import router as payroll_me_router
from hcns.app.routers.cham_cong import router as cham_cong_router
# Phụ thuộc GPS/công trình của trang Chấm công (bản union saleadmin) — gom luôn.
from hcns.app.routers.lenh_di_do import router as lenh_di_do_router
from hcns.app.routers.cong_trinh import router as cong_trinh_router
from hcns.app.routers.app_config import router as app_config_router
# Trang Hồ sơ cá nhân dùng chung (canonical=hcns) gọi /api/profile-workflow.
from hcns.app.routers.profile_workflow import router as profile_workflow_router


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

# ── Module DÙNG CHUNG (Core Services) — gom API về 1 container ──
# nginx sẽ route /api/xin-nghi, /api/duyet-chi, /api/cham-cong… của MỌI app về đây.
app.include_router(xin_nghi_router, prefix="/api/xin-nghi", tags=["xin-nghi"])
app.include_router(duyet_chi_router, prefix="/api/duyet-chi", tags=["duyet-chi"])
app.include_router(giao_viec_router, prefix="/api/giao-viec", tags=["giao-viec"])
app.include_router(calendar_router, prefix="/api/calendar", tags=["calendar"])
app.include_router(payroll_me_router, prefix="/api/payroll", tags=["payroll_me"])
app.include_router(cham_cong_router, prefix="/api/cham-cong", tags=["cham_cong"])
app.include_router(lenh_di_do_router, prefix="/api/lenh-di-do", tags=["lenh_di_do"])
app.include_router(cong_trinh_router, prefix="/api/cong-trinh", tags=["cong_trinh"])
app.include_router(app_config_router, prefix="/api/app-config", tags=["app_config"])
app.include_router(profile_workflow_router, prefix="/api/profile-workflow", tags=["profile_workflow"])


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


# ── Demo masking (che chỉ số kinh doanh cho tài khoản demo) — gắn NGOÀI CÙNG ──
from shared.middleware.demo_mask import install_demo_masking as _install_demo_masking  # noqa: E402
_install_demo_masking(app)
