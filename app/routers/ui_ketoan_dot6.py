"""HTML pages cho các màn Kế toán — đợt 6 của bản redesign giao diện.

Nguồn thiết kế: d:\\Papasanvn-sv1\\ketoan-giao-dien\\templates\\ketoan\\*.html
(đã copy nguyên văn sang templates/ phẳng của app này, không sửa).

4 màn:
    GET /ketoan/thue-gtgt   -- Thuế GTGT (bảng kê hoá đơn bán ra/mua vào theo kỳ)
                                   tính năng đề xuất, chưa có backend thật
    GET /ketoan/tam-ung     -- Tạm ứng nhân viên (TK 141) + quyết toán
                                   tính năng đề xuất, chưa có backend thật
    GET /ketoan/phan-bo     -- Chi phí chờ phân bổ (TK 242, trả trước/CCDC)
                                   tính năng đề xuất, chưa có backend thật
    GET /ketoan/cai-dat     -- Cài đặt Kế toán (đơn vị, năm TC, duyệt chi, đánh số, phân quyền)
                                   tính năng đề xuất, chưa có backend thật

Auth + templates dựng giống hệt app/routers/pages.py (house pattern của app này,
cũng là pattern đợt 7 đã dùng — ui_ketoan_dot7.py).
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
    """Giống hệt pages.py / bao_cao_duyet_chi.py / ui_ketoan_dot7.py — auth qua
    cookie JWT `access_token`, chưa đăng nhập thì redirect /login."""
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


@router.get("/thue-gtgt", response_class=HTMLResponse, name="kt_thue_gtgt")
def kt_thue_gtgt_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Thuế GTGT — bảng kê hoá đơn bán ra/mua vào theo kỳ kê khai, số phải nộp."""
    return templates.TemplateResponse(
        "kt_thue_gtgt.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/tam-ung", response_class=HTMLResponse, name="kt_tam_ung")
def kt_tam_ung_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Tạm ứng — khoản tạm ứng nhân viên (TK 141), hạn hoàn ứng và quyết toán."""
    return templates.TemplateResponse(
        "kt_tam_ung.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/phan-bo", response_class=HTMLResponse, name="kt_phan_bo")
def kt_phan_bo_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Chi phí chờ phân bổ — trả trước/CCDC (TK 242) và lịch phân bổ hằng tháng."""
    return templates.TemplateResponse(
        "kt_phan_bo.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/cai-dat", response_class=HTMLResponse, name="kt_cai_dat")
def kt_cai_dat_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Cài đặt Kế toán — đơn vị, năm tài chính/chính sách, duyệt chi, đánh số, phân quyền."""
    return templates.TemplateResponse(
        "kt_cai_dat.html",
        {"request": request, "user": user_ctx(user)},
    )
