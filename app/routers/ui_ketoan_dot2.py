"""HTML pages cho giao diện mới "đợt 2" của app Kế Toán — reskin theo hệ kd-/kt-.

4 màn của đợt này: Cân đối phát sinh, Danh mục tài khoản, Công nợ nhà cung cấp,
Bù trừ công nợ. Router TỰ CHỨA (auth + Jinja2Templates riêng) — không import gì
từ pages.py để tránh đụng nhau khi main.py wiring trung tâm ghép các router
đợt khác lại (mỗi đợt một file `ui_ketoan_dotN.py`).

Auth check qua cookie JWT (`access_token`) — copy nguyên mẫu từ app/routers/pages.py.
Dữ liệu thật gọi thẳng qua JS phía client (KD.api) tới các router /api/... đã có sẵn;
router này CHỈ render khung trang + truyền vài cờ quyền cho template.
"""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from shared.auth import JWTPayload
from shared.auth.jwt import verify_jwt
from shared.templates import setup_jinja2, user_ctx


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
setup_jinja2(templates)

router = APIRouter(prefix="/ketoan")

# Vai trò được phép TỰ POST bút toán thủ công (app/routers/journal.py:_ROLES_POST) —
# dùng để ẩn/khoá nút "Lập bút toán bù trừ" ở màn Bù trừ công nợ cho vai trò không
# đủ quyền, thay vì để họ bấm rồi ăn 403 từ POST /api/journal.
_ROLES_POST_JOURNAL = ("admin", "ceo", "assistant_ceo")


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


@router.get("/can-doi", response_class=HTMLResponse, name="ketoan_can_doi")
def can_doi_page(request: Request):
    """Cân đối phát sinh — dòng TK bấm sang Sổ cái đã lọc đúng TK + kỳ.

    Dữ liệu thật KHÔNG có endpoint "cân đối phát sinh" (dư đầu/PS/dư cuối theo
    từng TK) — kt-can-doi.js tự ghép từ 2 lần gọi
    GET /api/journal/balance-summary?den_ngay=... (đầu kỳ, cuối kỳ) +
    GET /api/journal/accounts (tên TK). Xem chú thích đầu file kt-can-doi.js.
    """
    user = _require_user_redirect(request)
    return templates.TemplateResponse(
        "kt_can_doi.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/tai-khoan", response_class=HTMLResponse, name="ketoan_tai_khoan")
def tai_khoan_page(request: Request):
    """Danh mục tài khoản.

    Đọc thật: GET /api/journal/accounts (chỉ mã + tên, KHÔNG có cấp/tính chất/
    đối tượng/trạng thái/ghi chú/đã phát sinh). Thêm/sửa/xoá/ngừng dùng gọi tới
    /api/danh-muc-tai-khoan (ĐỀ XUẤT — CHƯA có backend, xem báo cáo bàn giao).
    KHÔNG dùng /api/tai-khoan — path đó đã là API tài khoản NGÂN HÀNG/tiền mặt
    thật (app/routers/tai_khoan_nh.py) trong app này, đụng path nếu tái dùng.
    """
    user = _require_user_redirect(request)
    return templates.TemplateResponse(
        "kt_tai_khoan.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/cong-no-ncc", response_class=HTMLResponse, name="ketoan_cong_no_ncc")
def cong_no_ncc_page(request: Request):
    """Công nợ nhà cung cấp — data-ben="ncc" trên <main> (kt-cong-no.js dùng chung với KH).

    Đọc thật: GET /api/cong-no/ncc-module?filter=all (app/routers/cong_no_ncc.py) —
    kt-cong-no.js tự map field thật (supplier/doi_tac, don_list…) sang hình dạng
    khung chung qua CFG.ncc.chuyen(); lọc/sắp/phân trang làm ở trình duyệt vì
    ncc-module trả hết một lần, không hỗ trợ page/size/sort/tinh_trang phía máy chủ.
    """
    user = _require_user_redirect(request)
    return templates.TemplateResponse(
        "kt_cong_no_ncc.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/bu-tru", response_class=HTMLResponse, name="ketoan_bu_tru")
def bu_tru_page(request: Request):
    """Bù trừ công nợ — ghép khách/NCC theo TÊN đối tác (không phải MST — backend
    chưa có trường MST trên hồ sơ khách/NCC). Ghi sổ qua POST /api/journal thật
    (Nợ 331 / Có 131) — chỉ role admin/ceo/assistant_ceo được post (journal.py
    _ROLES_POST); các role khác thấy nút bị khoá kèm lý do, không bấm rồi ăn 403.
    """
    user = _require_user_redirect(request)
    return templates.TemplateResponse(
        "kt_bu_tru.html",
        {
            "request": request,
            "user": user_ctx(user),
            "co_the_lap_but_toan": user.role in _ROLES_POST_JOURNAL,
        },
    )
