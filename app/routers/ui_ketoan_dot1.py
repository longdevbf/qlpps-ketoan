"""HTML pages — Kế Toán giao diện mới, đợt 1 (Tổng quan · Sổ kế toán · Công nợ KH).

Router riêng, KHÔNG đăng ký trong app/main.py ở đây — phiên điều phối trung tâm
sẽ include_router(router) sau để tránh xung đột merge với các đợt khác đang
làm song song trên cùng main.py.

Auth: y hệt app/routers/pages.py — cookie JWT `access_token`, chưa đăng nhập
thì 307 redirect /login (copy boilerplate để file này tự đứng một mình).
"""
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from shared.auth import JWTPayload
from shared.auth.jwt import verify_jwt
from shared.templates import setup_jinja2, user_ctx


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
setup_jinja2(templates)

router = APIRouter(prefix="/ketoan")


def _optional_user(request: Request) -> Optional[JWTPayload]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        return verify_jwt(token)
    except Exception:
        return None


def _require_user_redirect(request: Request) -> JWTPayload:
    user = _optional_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"},
        )
    return user


@router.get("/tong-quan", response_class=HTMLResponse, name="ketoan_tong_quan")
def tong_quan_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Dashboard Kế toán — giao diện mới (giao diện cũ nếu có nằm ở route khác)."""
    return templates.TemplateResponse(
        "kt_tong_quan.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/so-cai", response_class=HTMLResponse, name="ketoan_so_cai")
def so_cai_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Sổ kế toán — một màn, hai chế độ (nhật ký chung / sổ cái theo TK)."""
    return templates.TemplateResponse(
        "kt_so_cai.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/cong-no-kh", response_class=HTMLResponse, name="ketoan_cong_no_kh")
def cong_no_kh_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Công nợ khách hàng — tổng hợp theo khách, mở rộng xem hoá đơn còn nợ."""
    return templates.TemplateResponse(
        "kt_cong_no_kh.html",
        {"request": request, "user": user_ctx(user)},
    )
