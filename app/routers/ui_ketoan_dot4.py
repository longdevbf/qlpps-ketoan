"""HTML pages cho đợt 4 của gói giao diện mới Kế Toán (nguồn:
`ketoan-giao-dien/templates/ketoan/*.html`, đã copy nguyên văn sang
templates/ phẳng của app này, không sửa HTML/CSS).

5 màn L4 (form / chi tiết), dùng QUERY PARAMS để chọn chế độ/bản ghi thay vì
một route riêng cho từng bản ghi. Các JS trang (`kt-chung-tu.js`,
`kt-tscd-phieu.js`, `kt-khoan-vay-phieu.js`, `kt-tscd-chi-tiet.js`,
`kt-doi-tuong.js`) tự đọc `location.search` qua `KT.url.doc()` (xem
`static/js/kt-chung.js`) — các tham số khai báo dưới đây KHÔNG được dùng ở
server (không truyền vào template context), chỉ để route tường minh chấp
nhận chúng và hiện trong OpenAPI docs thay vì phụ thuộc ngầm vào query string.

    GET /ketoan/chung-tu       ?loai=phieu_thu|phieu_chi|khac | ?id=
                                 -- Chứng từ kế toán (lập / xem / đảo)
                                 API thật: app/routers/journal.py (prefix /api/journal)
    GET /ketoan/tscd/phieu     ?id=&che_do=thanh_ly
                                 -- Phiếu TSCĐ (ghi tăng / sửa / thanh lý)
                                 API thật: app/routers/tai_san.py (prefix /api/tai-san)
    GET /ketoan/khoan-vay/phieu ?id=
                                 -- Hợp đồng vay (thêm / sửa)
                                 API thật: app/routers/khoan_vay.py (prefix /api/khoan-vay)
    GET /ketoan/tscd/chi-tiet  ?id=
                                 -- Chi tiết TSCĐ + lịch khấu hao
                                 API thật: app/routers/tai_san.py GET /api/tai-san/<id>
    GET /ketoan/doi-tuong      ?ben=kh|ncc&id=
                                 -- Chi tiết công nợ 1 khách hàng / nhà cung cấp
                                 API thật: app/routers/cong_no.py (KH — lọc theo `doi_tac`,
                                 KHÔNG có id khách ổn định) + app/routers/cong_no_ncc.py
                                 (NCC — GET /api/cong-no/ncc/<supplier_id>/detail)

Auth + templates dựng giống hệt app/routers/pages.py và các
ui_ketoan_dot5/7/8.py khác (house pattern của app này) — import thẳng
`_require_user_redirect` từ `.pages` thay vì khai lại.

Router CHƯA được include trong app/main.py — chờ pass sau (coordinating
session) gắn vào; KHÔNG tự sửa app/main.py ở đây.

── MISMATCH THẬT SỰ (backend đã có nhưng lệch mô hình so với thiết kế) ──
Ghi chi tiết từng điểm ở docstring đầu mỗi file JS trang. Tóm tắt (xem báo
cáo bàn giao để đầy đủ):
  1. `/api/tai-khoan` (mount từ tai_khoan_nh.py) trả DANH SÁCH TÀI KHOẢN
     NGÂN HÀNG/TIỀN MẶT của công ty (id, ten_tk, loai, so_tk…), KHÔNG PHẢI
     hệ thống tài khoản kế toán {ma, ten, cap, so_tk_con, dang_dung…} mà
     `KT.oTk` (static/js/kt-chung.js, DÙNG CHUNG cả 5 màn ở đây) hard-code
     gọi. Xung đột này ĐÃ được sibling session ghi nhận ở
     app/routers/ui_ketoan_dot8.py (đợt 8) — không tự ý đổi path ở đây.
     Hệ quả: mọi ô "chọn tài khoản kế toán" (KT.oTk) trên cả 5 màn L4 này
     sẽ hiện SAI dữ liệu (tài khoản ngân hàng thay vì mã TK) cho tới khi có
     quyết định chung (đổi path 1 bên, hoặc gộp response) — không sửa được
     từ trong router/JS của riêng đợt 4.
  2. `POST /api/journal` (tạo chứng từ) + `POST /api/journal/<id>/void`
     (đảo) chỉ cho phép role admin/ceo/assistant_ceo (`journal.py:_ROLES_POST`)
     — nhân viên kế toán thường (role `kt`/`manager`, vẫn xem được app qua
     `require_ketoan_user`) KHÔNG lập/đảo được chứng từ qua API thật. Cần
     chủ dự án quyết có nới quyền hay không.
  3. `/api/doi-tuong` (danh sách khách hàng/NCC/nhân viên cho ô chọn đối
     tượng) KHÔNG tồn tại ở backend thật.
  4. `/api/tscd/*` (theo README) không tồn tại — backend thật dùng
     `/api/tai-san/*` với model khác hẳn (không có tk_hao_mon/tk_cp/tk_doi_ung
     theo từng tài sản — account_code tự suy ra 211/213 theo `loai`; không
     hỗ trợ "cho vay" ở khoan_vay.py — chỉ có "đi vay").
Chi tiết & cách xử lý (ẩn/khoá field không có API tương ứng, đổi field
sang đúng tên thật…) nằm trong từng file JS.
"""
from typing import Annotated, Optional
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


@router.get("/chung-tu", response_class=HTMLResponse, name="kt_chung_tu")
def kt_chung_tu_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
    loai: Optional[str] = None,
    id: Optional[str] = None,
    kh: Optional[str] = None,
    ncc: Optional[str] = None,
    mau: Optional[str] = None,
    sao: Optional[str] = None,
):
    """Chứng từ kế toán — lập phiếu thu/phiếu chi/bút toán khác, xem, đảo.

    `loai`/`id`/`kh`/`ncc`/`mau`/`sao` chỉ khai để tường minh trong OpenAPI —
    `kt-chung-tu.js` tự đọc lại từ `location.search`.
    """
    return templates.TemplateResponse(
        "kt_chung_tu.html", {"request": request, "user": user_ctx(user)}
    )


@router.get("/tscd/phieu", response_class=HTMLResponse, name="kt_tscd_phieu")
def kt_tscd_phieu_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
    id: Optional[str] = None,
    che_do: Optional[str] = None,
):
    """Phiếu TSCĐ — ghi tăng / sửa / thanh lý.

    `id`/`che_do` chỉ khai để tường minh — `kt-tscd-phieu.js` tự đọc
    `location.search`.
    """
    return templates.TemplateResponse(
        "kt_tscd_phieu.html", {"request": request, "user": user_ctx(user)}
    )


@router.get(
    "/khoan-vay/phieu", response_class=HTMLResponse, name="kt_khoan_vay_phieu"
)
def kt_khoan_vay_phieu_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
    id: Optional[str] = None,
):
    """Hợp đồng vay — thêm / sửa (chỉ "đi vay" ở backend thật, xem docstring
    đầu file `kt-khoan-vay-phieu.js` — backend không có khái niệm "cho vay").
    """
    return templates.TemplateResponse(
        "kt_khoan_vay_phieu.html", {"request": request, "user": user_ctx(user)}
    )


@router.get("/tscd/chi-tiet", response_class=HTMLResponse, name="kt_tscd_chi_tiet")
def kt_tscd_chi_tiet_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
    id: Optional[str] = None,
):
    """Chi tiết TSCĐ — thẻ giá trị, lịch khấu hao, thông tin hạch toán."""
    return templates.TemplateResponse(
        "kt_tscd_chi_tiet.html", {"request": request, "user": user_ctx(user)}
    )


@router.get("/doi-tuong", response_class=HTMLResponse, name="kt_doi_tuong")
def kt_doi_tuong_page(
    request: Request,
    user: Annotated[JWTPayload, Depends(_require_user_redirect)],
    ben: Optional[str] = None,
    id: Optional[str] = None,
    tu: Optional[str] = None,
    den: Optional[str] = None,
):
    """Chi tiết công nợ một khách hàng (`ben=kh`) hoặc nhà cung cấp
    (`ben=ncc`). Xem docstring đầu file `kt-doi-tuong.js` — phía KH không có
    id khách ổn định ở backend thật (dùng tên đối tác làm khoá tạm)."""
    return templates.TemplateResponse(
        "kt_doi_tuong.html", {"request": request, "user": user_ctx(user)}
    )
