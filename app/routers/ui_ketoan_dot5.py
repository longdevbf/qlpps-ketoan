"""HTML pages cho đợt 5 của gói giao diện mới Kế Toán (nguồn:
`ketoan-giao-dien/templates/ketoan/`) — Khoá sổ, Duyệt chi, Đề nghị thanh
toán, Đề xuất thanh toán NCC, trang in A4.

Auth: cookie JWT `access_token` (cùng pattern `_require_user_redirect` với
`app/routers/pages.py` / `app/routers/bao_cao_duyet_chi.py`) — chưa login →
redirect /login.

3 route dưới đây "đè" lên tính năng của 3 router CŨ hơn (design thay hẳn màn
cũ, xem README `ketoan-giao-dien` mục đợt 5). KHÔNG động vào các router cũ —
một pass khác sẽ deregister chúng khỏi app/main.py:
  - GET /ketoan/kt-duyet    thay cho `app/routers/kt_duyet.py`    (trang cũ tại GET /kt-duyet, template `kt_duyet.html` — đã bị đè bởi bản mới cùng tên)
  - GET /ketoan/de-nghi-tt  thay cho `app/routers/de_nghi_tt.py`  (trang cũ tại GET /de-nghi-tt, định nghĩa trong `app/routers/pages.py`, template `de_nghi_tt.html` — KHÔNG đụng, tên tệp khác)
  - GET /ketoan/de-xuat-ncc thay cho `app/routers/ncc_de_xuat.py` (trang cũ tại GET /duyet-ncc, định nghĩa trong `app/routers/pages.py`, template `ncc_de_xuat.html` — KHÔNG đụng, tên tệp khác)

Router CHƯA được include trong app/main.py — chờ pass sau gắn vào.

Các API `/api/khoa-so`, `/api/duyet-chi`, `/api/doi-tuong`, v.v. mà JS các
trang này gọi PHẦN LỚN CHƯA CÓ ở backend thật (tính năng đề xuất mới) — các
trang tự xử lý lỗi/rỗng khi API 404, không cần dựng backend ở đây.
"""
from pathlib import Path
from typing import Annotated

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


@router.get("/khoa-so", response_class=HTMLResponse, name="ui_dot5_khoa_so")
def khoa_so_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Kết chuyển cuối kỳ & khoá sổ."""
    return templates.TemplateResponse(
        "kt_khoa_so.html", {"request": request, "user": user_ctx(user)}
    )


@router.get("/kt-duyet", response_class=HTMLResponse, name="ui_dot5_kt_duyet")
def kt_duyet_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Duyệt chi (L3) — vẽ lại thay `kt_duyet.html` cũ."""
    return templates.TemplateResponse(
        "kt_duyet_new.html", {"request": request, "user": user_ctx(user)}
    )


@router.get("/de-nghi-tt", response_class=HTMLResponse, name="ui_dot5_de_nghi_tt")
def de_nghi_tt_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Form L4 — Tạo đề nghị thanh toán."""
    return templates.TemplateResponse(
        "kt_de_nghi_tt.html", {"request": request, "user": user_ctx(user)}
    )


@router.get("/de-xuat-ncc", response_class=HTMLResponse, name="ui_dot5_de_xuat_ncc")
def de_xuat_ncc_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Form L4 — Đề xuất thanh toán NCC. Thay `ncc_de_xuat.html` cũ."""
    return templates.TemplateResponse(
        "kt_de_xuat_ncc.html", {"request": request, "user": user_ctx(user)}
    )


@router.get("/in", response_class=HTMLResponse, name="ui_dot5_kt_in")
def kt_in_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Trang in A4 dùng chung (chứng từ / đối chiếu / báo cáo / đề nghị).

    JS phía client (`kt-in.js`) tự đọc query param `loai` — route không cần
    tách nhánh theo `loai` ở server.
    """
    return templates.TemplateResponse(
        "kt_in.html", {"request": request, "user": user_ctx(user)}
    )
