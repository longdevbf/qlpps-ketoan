"""HTML pages — Kế Toán giao diện mới, đợt 3a (nhóm 3+4 báo cáo tài chính + TSCĐ/vay/LN).

6 màn:
  GET /ketoan/bao-cao/kqkd     — Kết quả kinh doanh (B02-DN)
  GET /ketoan/bao-cao/cdkt     — Báo cáo tình hình tài chính (B01-DN)
  GET /ketoan/bao-cao/lctt     — Lưu chuyển tiền tệ (B03-DN) + dự báo 8 tuần
  GET /ketoan/tscd             — Tài sản cố định + khấu hao
  GET /ketoan/khoan-vay        — Khoản vay
  GET /ketoan/phan-phoi-ln     — Phân phối lợi nhuận

Auth check qua cookie JWT (`access_token`) — cùng khuôn với app/routers/pages.py.
Router này KHÔNG tự đăng ký vào app.main — main.py wire tập trung ở bước sau.
"""
from typing import Annotated, Optional
from pathlib import Path

from fastapi import APIRouter, Depends, Request, HTTPException, status
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


_User = Annotated[JWTPayload, Depends(_require_user_redirect)]


@router.get("/bao-cao/kqkd", response_class=HTMLResponse, name="kt_bao_cao_kqkd")
def kt_bao_cao_kqkd(request: Request, user: _User):
    return templates.TemplateResponse(
        "kt_kqkd.html", {"request": request, "user": user_ctx(user)}
    )


@router.get("/bao-cao/cdkt", response_class=HTMLResponse, name="kt_bao_cao_cdkt")
def kt_bao_cao_cdkt(request: Request, user: _User):
    return templates.TemplateResponse(
        "kt_cdkt.html", {"request": request, "user": user_ctx(user)}
    )


@router.get("/bao-cao/lctt", response_class=HTMLResponse, name="kt_bao_cao_lctt")
def kt_bao_cao_lctt(request: Request, user: _User):
    return templates.TemplateResponse(
        "kt_lctt.html", {"request": request, "user": user_ctx(user)}
    )


@router.get("/tscd", response_class=HTMLResponse, name="kt_tscd")
def kt_tscd(request: Request, user: _User):
    return templates.TemplateResponse(
        "kt_tscd.html", {"request": request, "user": user_ctx(user)}
    )


@router.get("/khoan-vay", response_class=HTMLResponse, name="kt_khoan_vay")
def kt_khoan_vay(request: Request, user: _User):
    return templates.TemplateResponse(
        "kt_khoan_vay.html", {"request": request, "user": user_ctx(user)}
    )


@router.get("/phan-phoi-ln", response_class=HTMLResponse, name="kt_phan_phoi_ln")
def kt_phan_phoi_ln(request: Request, user: _User):
    return templates.TemplateResponse(
        "kt_phan_phoi.html", {"request": request, "user": user_ctx(user)}
    )
