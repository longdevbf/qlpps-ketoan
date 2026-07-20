"""Báo Cáo Duyệt Chi (Kế Toán) — serve dashboard HTML page.

Page `/bao-cao/duyet-chi` render template `bao_cao_duyet_chi.html`. JS phía
client gọi các API có sẵn `/api/duyet-chi/*` (list / queue/me / stats /
report) — router này KHÔNG khai báo API mới.

Auth: cookie JWT (giống pages.py). Trang chỉ hiển thị, kt/manager/ceo có
quyền duyệt khi đơn ở approval_level='ketoan'.
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

router = APIRouter()


def _require_user_redirect(request: Request) -> JWTPayload:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"},
        )
    try:
        return verify_jwt(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"},
        )


@router.get(
    "/bao-cao/duyet-chi",
    response_class=HTMLResponse,
    name="bao_cao_duyet_chi",
)
def bao_cao_duyet_chi_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Dashboard Báo Cáo Duyệt Chi cho app Kế Toán.

    Render template — toàn bộ data fetch qua API có sẵn ở client.
    """
    return templates.TemplateResponse(
        "bao_cao_duyet_chi.html",
        {"request": request, "user": user_ctx(user)},
    )
