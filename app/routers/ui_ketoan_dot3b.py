"""HTML pages — đợt 3b (nhóm 5 của giao diện mới): Sổ quỹ, Ngân hàng, Doanh thu và
chi phí, Lương và BHXH, Đơn hàng — tài chính.

Reskin theo `d:\\Papasanvn-sv1\\ketoan-giao-dien` (hệ giao diện `kt-` prefix, không
Bootstrap). Router RIÊNG, cố ý không tự `include_router` ở đây — main.py wiring do
phiên điều phối trung tâm làm sau khi review.

Auth: cookie `access_token` (JWT) — pattern copy nguyên từ `app/routers/pages.py`
(KHÔNG dùng `require_ketoan_user` kiểu API vì đây là trang HTML, cần redirect
/login thay vì trả 401/403 JSON).
"""
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
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


_User = Annotated[JWTPayload, Depends(_require_user_redirect)]


@router.get("/so-quy", response_class=HTMLResponse, name="kt_so_quy")
def so_quy_page(request: Request, user: _User):
    """Sổ quỹ — MỌI quỹ đang hoạt động (tiền mặt TK 111 + ngân hàng TK 112).

    Mở phạm vi 02/10/2026: trước đó màn chỉ hiện tài khoản `loai='tien_mat'`.
    Dữ liệu thật: /api/so-quy, /api/so-quy/summary, /api/tai-khoan.
    """
    return templates.TemplateResponse(
        "kt_so_quy.html", {"request": request, "user": user_ctx(user)}
    )


@router.get("/ngan-hang", response_class=HTMLResponse, name="kt_ngan_hang")
def ngan_hang_page(request: Request, user: _User):
    """Ngân hàng + tiền mặt — danh mục & sổ giao dịch từng tài khoản.

    Dữ liệu thật: /api/tai-khoan (CRUD TaiKhoanNH), /api/tai-khoan/{id}/giao-dich
    + /so-du (TaiKhoanNHGiaoDich). KHÔNG có API đối soát sao kê ngân hàng thật —
    xem báo cáo cuối phiên (dot3b) để biết chi tiết phần đã lược bỏ/thay thế.
    """
    return templates.TemplateResponse(
        "kt_ngan_hang.html", {"request": request, "user": user_ctx(user)}
    )


@router.get("/thu-chi", response_class=HTMLResponse, name="kt_thu_chi")
def thu_chi_page(request: Request, user: _User):
    """Doanh thu và chi phí (3 tab). Dữ liệu thật: /api/doanh-thu, /api/chi-phi,
    /api/co-dinh (map cho tab "Chi phí cố định" — README gọi là "co_dinh")."""
    return templates.TemplateResponse(
        "kt_thu_chi.html", {"request": request, "user": user_ctx(user)}
    )


@router.get("/luong", response_class=HTMLResponse, name="kt_luong")
def luong_page(request: Request, user: _User):
    """Lương và BHXH (chỉ xem). Dữ liệu thật: GET /api/external/luong?thang=
    (đọc live từ hcns.app.routers.payroll.bang_luong_thang, cross-app cùng process)."""
    return templates.TemplateResponse(
        "kt_luong.html", {"request": request, "user": user_ctx(user)}
    )


@router.get("/don-hang-tai-chinh", name="kt_don_hang_tai_chinh")
def don_hang_tai_chinh_page(user: _User):
    """Bản đợt 3 đã gộp vào /ketoan/don-hang (cùng template + JS) — giữ URL cũ, chuyển hướng."""
    return RedirectResponse("/ketoan/don-hang", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
