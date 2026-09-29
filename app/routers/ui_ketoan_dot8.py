"""HTML pages cho các màn Kế toán — đợt 8 của bản redesign giao diện.

Nguồn thiết kế: d:\\Papasanvn-sv1\\ketoan-giao-dien\\templates\\ketoan\\*.html
(đã copy nguyên văn sang templates/ phẳng của app này, không sửa).

4 màn:
    GET /ketoan/bhxh           -- Bảo hiểm xã hội (chỉ xem, đọc từ HCNS)
                                   API thật: app/routers/external.py (GET /api/external/bhxh)
    GET /ketoan/quang-cao      -- Chi phí quảng cáo + phân bổ CPA (2 tab)
                                   API thật: app/routers/external.py (GET /api/external/ads),
                                   app/routers/bao_cao_cpa.py (GET /api/bao-cao/cpa*),
                                   app/routers/ads_phan_bo.py (POST /api/ads-phan-bo/recalc/<thang>)
    GET /ketoan/loai-chi-phi   -- Danh mục loại chi phí (nhóm 641/642/635/811)
                                   API thật: app/routers/loai_chi_phi.py (GET/POST/PUT/DELETE /api/loai-chi-phi)
    GET /ketoan/quy            -- Quản lý quỹ nội bộ (cây quỹ, nạp/chi, lịch sử)
                                   API thật: app/routers/quy_dn.py (GET /api/quy/tree,
                                   POST/PUT/DELETE /api/quy/..., + giao_dich_router mount /api/quy-dn/...)

Auth + templates dựng giống hệt app/routers/pages.py và ui_ketoan_dot7.py
(house pattern của app này).

LƯU Ý (không sửa ở đây — vấn đề backend, không phải router file này):
kt_quy.html / kt-quy.js gọi GET /api/tai-khoan?active_only=true để lấy danh sách
tài khoản tiền đối ứng (tiền mặt/ngân hàng) cho ô "nạp/chi". Path này ĐÃ bị
app/routers/tai_khoan_nh.py chiếm dụng (mount prefix "/api/tai-khoan" trong
main.py, CRUD tài khoản NH/tiền mặt) — đúng mục đích kt-quy.js cần, NHƯNG theo
README đợt 8, màn "Danh mục tài khoản" mới của đợt 1/2 (sibling session) cũng
muốn dùng cùng path này cho một mục đích khác (toàn bộ hệ thống tài khoản kế
toán / chart of accounts). Đây là xung đột path ở tầng backend, cần bên sở hữu
đợt 1/2 hoặc chủ trì chung quyết định (đổi path một bên, hoặc gộp response) —
không tự ý đổi trong file router này.
"""
from typing import Annotated
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from shared.auth import JWTPayload
from shared.templates import setup_jinja2, user_ctx

from .pages import _require_user_redirect


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
setup_jinja2(templates)

router = APIRouter(prefix="/ketoan")


@router.get("/bhxh", response_class=HTMLResponse, name="kt_bhxh")
def kt_bhxh_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Bảo hiểm xã hội — chỉ xem, mức đóng BHXH/BHYT/BHTN theo hồ sơ HCNS."""
    return templates.TemplateResponse(
        "kt_bhxh.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/quang-cao", response_class=HTMLResponse, name="kt_quang_cao")
def kt_quang_cao_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Chi phí quảng cáo — tab chi phí theo ngày/kênh + tab phân bổ CPA về đơn hàng."""
    return templates.TemplateResponse(
        "kt_quang_cao.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/loai-chi-phi", response_class=HTMLResponse, name="kt_loai_chi_phi")
def kt_loai_chi_phi_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Loại chi phí — danh mục phân loại phiếu chi/đề nghị thanh toán, gắn TK 641/642/635/811."""
    return templates.TemplateResponse(
        "kt_loai_chi_phi.html",
        {"request": request, "user": user_ctx(user)},
    )


@router.get("/quy", response_class=HTMLResponse, name="kt_quy")
def kt_quy_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
):
    """Quản lý quỹ nội bộ — cây quỹ, nạp/chi, lịch sử giao dịch từng quỹ."""
    return templates.TemplateResponse(
        "kt_quy.html",
        {"request": request, "user": user_ctx(user)},
    )
