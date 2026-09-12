"""HTML pages cho app Kế Toán — Jinja2 templates port từ V1.

Auth check qua cookie JWT (`access_token`); nếu chưa login → redirect /login.
"""
from typing import Annotated, Optional
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from shared.auth import JWTPayload
from shared.auth.jwt import verify_jwt
from shared.templates import setup_jinja2, user_ctx


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
setup_jinja2(templates)

router = APIRouter()


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


@router.get("/login", response_class=HTMLResponse, name="login")
def login_page(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": error}
    )


@router.post("/login")
async def login_submit(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    remember: Annotated[Optional[str], Form()] = None,
):
    """Forward credentials → auth_service /auth/login → set cookie + redirect /."""
    import httpx
    from shared.config import settings as _s

    auth_url = f"http://{_s.auth_host}:{_s.auth_port}/auth/login"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.post(auth_url, json={"username": username, "password": password})
        except Exception as e:
            return RedirectResponse(f"/login?error=Không kết nối được Auth: {e}",
                                    status_code=status.HTTP_303_SEE_OTHER)

    if r.status_code != 200:
        msg = "Sai username hoặc password"
        try:
            msg = r.json().get("error", msg)
        except Exception:
            pass
        return RedirectResponse(f"/login?error={msg}", status_code=status.HTTP_303_SEE_OTHER)

    data = r.json()
    # Check app permission BEFORE setting cookie
    try:
        from shared.auth.jwt import decode_token
        _payload = decode_token(data["access_token"])
        _allowed = ("admin", "ceo", "assistant_ceo")
        if _payload.role not in _allowed and "ketoan" not in (_payload.apps or []):
            return RedirectResponse(
                f"/login?error=Tài khoản {_payload.username} (vai trò {_payload.role}) không có quyền truy cập app ketoan",
                status_code=status.HTTP_303_SEE_OTHER,
            )
    except Exception:
        pass  # decode fail → để set_cookie xử lý 401 sau
    redirect = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(
        key="access_token",
        value=data["access_token"],
        max_age=data.get("expires_in", _s.jwt_access_ttl_min * 60),
        httponly=True,
        secure=not _s.is_dev,
        samesite="lax",
        domain=None if _s.is_dev else ".qlpps.com",
    )
    return redirect


@router.get("/logout", name="logout")
def logout(request: Request):
    # Mark offline khi user logout — clear Redis chat:online:{username} ngay
    try:
        from shared.auth.jwt import verify_jwt
        from shared.utils.presence import mark_offline
        tok = request.cookies.get("access_token")
        if tok:
            payload = verify_jwt(tok)
            mark_offline(payload.username)
    except Exception:
        pass
    redirect = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    redirect.delete_cookie("access_token")
    return redirect


@router.get("/", response_class=HTMLResponse, name="root")
def root(request: Request):
    """V1: nếu chưa login → /login, đã login → /app."""
    user = _optional_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/app", status_code=status.HTTP_302_FOUND)


@router.get("/app", response_class=HTMLResponse, name="index")
def index_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/dao-tao", response_class=HTMLResponse, name="dao_tao")
def dao_tao_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    return templates.TemplateResponse(
        "dao_tao.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/xin-nghi", response_class=HTMLResponse, name="xin_nghi")
def xin_nghi_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    return templates.TemplateResponse(
        "xin_nghi.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/bang-luong-thang", response_class=HTMLResponse, name="bang_luong_thang")
def bang_luong_thang_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Bảng lương cá nhân — màn dùng chung, số liệu lấy từ /api/payroll/me."""
    return templates.TemplateResponse(
        "bang_luong_thang.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/duyet-chi", response_class=HTMLResponse, name="duyet_chi")
def duyet_chi_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    return templates.TemplateResponse(
        "duyet_chi.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/de-xuat", response_class=HTMLResponse, name="de_xuat")
def de_xuat_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    return templates.TemplateResponse(
        "de_xuat.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/chi-tap-trung", response_class=HTMLResponse, name="chi_tap_trung")
def chi_tap_trung_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Trung tâm Chi — gom mọi khoản chờ chi (đề xuất chi, trả NCC) về 1 nơi,
    KT bấm Chi ở từng tab → tự lên sổ quỹ (anh Quang 2026-08-24)."""
    return templates.TemplateResponse(
        "chi_tap_trung.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/giao-viec", response_class=HTMLResponse, name="giao_viec")
def giao_viec_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    resp = templates.TemplateResponse(
        "giao_viec.html",
        {"request": request, "user": user_ctx(user)},
    )
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@router.get("/lich-lam-viec", response_class=HTMLResponse, name="lich_lam_viec")
def lich_lam_viec_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    resp = templates.TemplateResponse(
        "lich_lam_viec.html",
        {"request": request, "user": user_ctx(user)},
    )
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@router.get("/products", response_class=HTMLResponse, name="products")
def products_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """M1 — Sản phẩm + Tồn kho + BOM (tabs)."""
    return templates.TemplateResponse(
        "products.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/logout", name="logout")
def logout(request: Request):
    """Xoá cookie access_token rồi redirect /login."""
    resp = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    resp.delete_cookie("access_token")
    return resp

@router.get("/cham-cong", response_class=HTMLResponse)
def cham_cong_page(request: Request, user: Annotated[JWTPayload, Depends(_require_user_redirect)] = None):
    if user is None: user = _require_user_redirect(request)
    return templates.TemplateResponse("cham_cong.html", {"request": request, "user": user_ctx(user)})

@router.get("/phe-duyet", response_class=HTMLResponse)
def phe_duyet_page(request: Request, user: Annotated[JWTPayload, Depends(_require_user_redirect)] = None):
    if user is None: user = _require_user_redirect(request)
    return templates.TemplateResponse("phe_duyet.html", {"request": request, "user": user_ctx(user)})


@router.get("/de-nghi-tt", response_class=HTMLResponse, name="de_nghi_tt")
def de_nghi_tt_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """KT duyệt cấp 1 các Đề nghị thanh toán từ saleadmin."""
    return templates.TemplateResponse(
        "de_nghi_tt.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/duyet-ncc", response_class=HTMLResponse, name="duyet_ncc")
def duyet_ncc_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """KT duyệt cấp 1 các Đề Xuất Trả NCC từ muahang.congno."""
    return templates.TemplateResponse(
        "ncc_de_xuat.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/khuyen-mai", response_class=HTMLResponse, name="khuyen_mai")
def khuyen_mai_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Khuyến mãi — đọc proxy marketing.khuyen_mai + tài chính KM."""
    return templates.TemplateResponse(
        "khuyen_mai.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/ho-so-ca-nhan", response_class=HTMLResponse, name="ho_so_ca_nhan")
def ho_so_ca_nhan_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Anh Quang 2026-06-06: Hồ sơ cá nhân hiển thị TẠI app NV đang dùng,
    không link sang HCNS. Template + endpoint /api/payroll/me cùng share."""
    resp = templates.TemplateResponse(
        "ho_so_ca_nhan.html",
        {"request": request, "user": user_ctx(user)},
    )
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp
