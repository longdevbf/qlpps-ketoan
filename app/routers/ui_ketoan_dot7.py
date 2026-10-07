"""HTML pages cho các màn Kế toán — đợt 7 của bản redesign giao diện.

Nguồn thiết kế: d:\\Papasanvn-sv1\\ketoan-giao-dien\\templates\\ketoan\\*.html
(đã copy nguyên văn sang templates/ phẳng của app này, không sửa).

6 màn:
    GET /ketoan/don-hang          -- Đơn hàng (đối chiếu KT + bàn giao + tối ưu CK)
                                       API thật: app/routers/external.py
    GET /ketoan/san-pham          -- Danh mục sản phẩm dùng chung
                                       API thật: app/routers/products.py
    GET /ketoan/ton-kho           -- Tồn kho theo mã hàng (Kho mới Mua hàng: kho_sp + kho_movement)
                                       API thật: app/routers/external.py (ton-kho-mh)
    GET /ketoan/thuoc-tinh        -- Thuộc tính sản phẩm (master-detail 3 bước)
                                       API thật: app/routers/product_attributes.py
    GET /ketoan/so-du-dau-ky      -- Số dư đầu kỳ (tính năng đề xuất, chưa có backend)
    GET /ketoan/thue-tncn-tndn    -- Thuế TNCN/TNDN (tính năng đề xuất, chưa có backend)

Auth + templates dựng giống hệt app/routers/pages.py (house pattern của app này).
"""
from typing import Annotated
from pathlib import Path

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
    """Giống hệt pages.py / bao_cao_duyet_chi.py — auth qua cookie JWT
    `access_token`, chưa đăng nhập thì redirect /login."""
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


@router.get("/don-hang", response_class=HTMLResponse, name="kt_don_hang")
def kt_don_hang_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Đơn hàng — 3 tab: đối chiếu kế toán, bàn giao trong ngày, tối ưu chiết khấu."""
    return templates.TemplateResponse(
        "kt_don_hang.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/san-pham", response_class=HTMLResponse, name="kt_san_pham")
def kt_san_pham_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Sản phẩm — danh mục dùng chung toàn hệ, Kế toán là nơi duy nhất thêm/sửa/xoá."""
    return templates.TemplateResponse(
        "kt_san_pham.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/ton-kho", response_class=HTMLResponse, name="kt_ton_kho")
def kt_ton_kho_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Tồn kho — theo mã hàng ở Kho mới của Mua hàng (chỉ đọc); KT chỉ đặt giá bán."""
    return templates.TemplateResponse(
        "kt_ton_kho.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/thuoc-tinh", response_class=HTMLResponse, name="kt_thuoc_tinh")
def kt_thuoc_tinh_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Thuộc tính sản phẩm — master-detail 3 bước (nhóm master → sản phẩm → thuộc tính)."""
    return templates.TemplateResponse(
        "kt_thuoc_tinh.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/so-du-dau-ky", response_class=HTMLResponse, name="kt_so_du_dau_ky")
def kt_so_du_dau_ky_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Số dư đầu kỳ — tính năng đề xuất, chưa có backend thật; trang sẽ hiện
    trạng thái rỗng/lỗi khi gọi /api/so-du-dau-ky (đúng như kỳ vọng đợt 7)."""
    return templates.TemplateResponse(
        "kt_so_du_dau_ky.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/thue-tncn-tndn", response_class=HTMLResponse, name="kt_thue_tncn_tndn")
def kt_thue_tncn_tndn_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Thuế TNCN/TNDN — tính năng đề xuất, chưa có backend thật; trang sẽ hiện
    trạng thái rỗng/lỗi khi gọi /api/thue-tncn, /api/thue-tndn (đúng như kỳ vọng đợt 7)."""
    return templates.TemplateResponse(
        "kt_thue_tncn_tndn.html",
        {"request": request, "user": user_ctx(user)},
    )
