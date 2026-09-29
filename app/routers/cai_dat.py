"""Cài đặt Kế toán — `/ketoan/cai-dat` (5 tab: đơn vị / chính sách / duyệt chi /
đánh số / phân quyền). Trước 2026-09-25 không có bảng/endpoint nào — trang chỉ
là mock JS (README/khảo sát: GET /api/cai-dat · PUT /api/cai-dat/<phan>).

Endpoints:
    GET  /api/cai-dat                 -- cả 5 tab trong 1 lần gọi (mọi role ketoan)
    PUT  /api/cai-dat/don_vi          -- sửa letterhead (bảng ketoan.don_vi)
    PUT  /api/cai-dat/ke_toan         -- sửa chế độ/chính sách kế toán
    PUT  /api/cai-dat/danh_so         -- sửa quy tắc đánh số (lưu — CHƯA đấu
                                          vào `services/journal.py:next_ma_but_toan`,
                                          xem docstring model CaiDatHeThong)
    PUT  /api/cai-dat/duyet_chi       -- 400: tab này CHỈ ĐỌC (xem bên dưới)
    PUT  /api/cai-dat/phan_quyen      -- 400: tab này CHỈ ĐỌC (xem bên dưới)

Sửa (PUT thật) yêu cầu `require_ceo_thuchi` (admin/ceo/assistant_ceo) — cùng
mức với quyền sửa/xoá lệnh thu-chi, vì đây là cấu hình áp dụng toàn hệ thống,
không phải nghiệp vụ hằng ngày của Kế Toán viên.

Tab "Duyệt chi" và "Phân quyền" KHÔNG có bảng cấu hình riêng — thiết kế màn
hình (mock) đề xuất một ma trận quyền chi tiết (xem/ghi_so/khoá_sổ/duyệt_chi/
xem_lương/sửa_danh_mục/cài_đặt) và ngưỡng duyệt theo số tiền mà HỆ THỐNG HIỆN
KHÔNG CÓ — phân quyền thật chỉ có 1 role JWT/người dùng (`shared.users.role`)
và vài hằng số role-tuple rải trong code (`app/routers/journal.py:_ROLES_POST`,
`app/routers/_deps.py:_CEO_THUCHI_ROLES/_KETOAN_ROLES`,
`shared/routers/duyet_chi.py:_can_approve_at`). Thay vì tạo bảng "phân quyền"
giả rồi không ai đọc, 2 tab này ĐỌC THẲNG các hằng số đó và hiển thị read-only
— trung thực với người dùng, còn sửa thật thì phải sửa code (anh Quang 2026-09-25).
"""
import calendar
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db
from shared.models import User

from ..models.cai_dat_he_thong import CaiDatHeThong
from ..models.journal_entry import JournalEntry
from ..models.ky_ke_toan import KyKeToan
from ..schemas.cai_dat import DanhSoRuleIn, DonViIn, KeToanSettingsIn
from ._deps import _CEO_THUCHI_ROLES, require_ceo_thuchi, require_ketoan_user
from .don_vi import don_vi_to_dict, get_or_seed_don_vi
from .journal import _ROLES_POST as _JOURNAL_POST_ROLES

try:
    # Nguồn thật của luồng duyệt cross-app (manager → ketoan → ceo).
    from shared.routers.duyet_chi import _CEO_ROLES as _DC_CEO_ROLES
except Exception:  # pragma: no cover — fail-soft nếu module đổi tên hằng số
    _DC_CEO_ROLES = {"admin", "ceo", "assistant_ceo"}


router = APIRouter()
_AUTH = Depends(require_ketoan_user)
_EDIT_AUTH = Depends(require_ceo_thuchi)


# ─── Helpers ──────────────────────────────────────────────────────────────

def _get_or_seed_settings(db: Session) -> CaiDatHeThong:
    st = db.get(CaiDatHeThong, 1)
    if st is None:
        st = CaiDatHeThong(id=1, danh_so=[])
        db.add(st)
        db.commit()
        db.refresh(st)
    return st


def _ke_toan_to_dict(st: CaiDatHeThong) -> dict:
    return {
        "che_do": st.che_do,
        "nam_tc_bat_dau": st.nam_tc_bat_dau,
        "tien_te": st.tien_te,
        "ngay_bat_dau_dung": st.ngay_bat_dau_dung.isoformat() if st.ngay_bat_dau_dung else None,
        "gia_xuat_kho": st.gia_xuat_kho,
        "khau_hao": st.khau_hao,
        "ky_ke_khai_thue": st.ky_ke_khai_thue,
    }


def _khoa_so_den(db: Session) -> Optional[str]:
    """Ngày cuối cùng đã khoá sổ — lấy THẬT từ `ketoan.ky_ke_toan` (M5), không
    phải cột lưu riêng, để không lệch với trang Khoá sổ."""
    thang = db.execute(
        select(KyKeToan.thang)
        .where(KyKeToan.trang_thai == "da_chot")
        .order_by(KyKeToan.thang.desc())
        .limit(1)
    ).scalar()
    if not thang:
        return None
    y, m = int(thang[:4]), int(thang[5:7])
    return date(y, m, calendar.monthrange(y, m)[1]).isoformat()


def _duyet_chi_info() -> dict:
    """Mô tả THẬT luồng duyệt chi + ai được post/void/sửa-xoá — đọc trực tiếp
    từ hằng số trong code (xem docstring module) để không lệch với cái đang
    thật sự gate request."""
    return {
        "cap_duyet": [
            {
                "cap": "truong_bo_phan",
                "ten": "Trưởng bộ phận",
                "dieu_kien": (
                    "Chỉ áp dụng nếu phòng/app của người đề nghị đang có "
                    "Trưởng bộ phận (manager/leader) hoạt động — nếu không, "
                    "đề nghị bắt đầu thẳng ở cấp Kế toán."
                ),
                "vai_tro_duyet": ["manager", "leader"],
            },
            {
                "cap": "ke_toan",
                "ten": "Kế toán",
                "dieu_kien": (
                    "Manager / Leader / Kế toán viên được cấp quyền vào "
                    "app Kế toán"
                ),
                "vai_tro_duyet": ["manager", "leader", "kt"],
            },
            {
                "cap": "ceo",
                "ten": "CEO",
                "dieu_kien": "Cấp duyệt cuối cùng trước khi chi tiền",
                "vai_tro_duyet": sorted(_DC_CEO_ROLES),
            },
        ],
        "ghi_so_but_toan_tay": {
            "vai_tro": sorted(_JOURNAL_POST_ROLES),
            "ghi_chu": (
                "Lập/đảo bút toán kế toán TAY (ghi thẳng vốn/doanh thu/tiền) — "
                "chỉ các vai trò này được post/void, tránh cửa hậu tự tăng vốn "
                "hoặc chế doanh thu."
            ),
        },
        "sua_xoa_thu_chi": {
            "vai_tro": sorted(_CEO_THUCHI_ROLES),
            "ghi_chu": (
                "Sửa/xoá lệnh thu-chi đã lập (sổ quỹ, doanh thu, chi phí) — "
                "Kế toán viên chỉ được tạo mới, không được sửa/xoá."
            ),
        },
        "chua_ho_tro": (
            "Hệ thống duyệt theo vai trò và phòng ban, chưa có ngưỡng duyệt "
            "theo số tiền hay chọn đích danh người duyệt — muốn đổi luồng "
            "duyệt cần yêu cầu bộ phận IT."
        ),
    }


def _phan_quyen_info(db: Session) -> dict:
    """Vai trò THẬT (JWT role) + ai đang giữ — đọc trực tiếp `shared.users`."""
    rows = db.execute(
        select(User.full_name, User.role, User.apps).where(User.active.is_(True))
    ).all()
    admin_ceo = sorted({
        r.full_name for r in rows if (r.role or "").lower() in _CEO_THUCHI_ROLES
    })
    ke_toan_vien = sorted({
        r.full_name for r in rows
        if (r.role or "").lower() in ("manager", "kt") and "ketoan" in (r.apps or [])
    })
    return {
        "vai_tro": [
            {
                "ma": "admin_ceo",
                "ten": "Admin / CEO / Trợ lý CEO",
                "nguoi": admin_ceo,
                "quyen": [
                    "Xem toàn bộ số liệu Kế Toán",
                    "Lập & đảo bút toán kế toán tay (ghi thẳng vốn/doanh thu/tiền)",
                    "Sửa/xoá lệnh thu-chi đã lập (sổ quỹ, doanh thu, chi phí)",
                    "Duyệt chi ở mọi cấp (Trưởng bộ phận, Kế toán, CEO)",
                    "Truy cập & sửa trang Cài đặt Kế toán",
                ],
            },
            {
                "ma": "manager_kt",
                "ten": "Manager / Kế toán viên có quyền vào app Kế toán",
                "nguoi": ke_toan_vien,
                "quyen": [
                    "Xem số liệu Kế Toán",
                    "Tạo mới thu-chi, doanh thu, chi phí, công nợ, sổ quỹ",
                    "Duyệt chi ở cấp “Kế toán” (giữa Trưởng bộ phận và CEO)",
                    "KHÔNG lập/đảo được bút toán tay, KHÔNG sửa/xoá được lệnh thu-chi đã lập",
                    "Xem được trang Cài đặt Kế toán nhưng KHÔNG sửa được",
                ],
            },
            {
                "ma": "khac",
                "ten": "Vai trò khác (kd, mkt, mh, sa, hr, nhân viên…)",
                "nguoi": [],
                "quyen": ["Không truy cập được app Kế Toán — API trả 403 Forbidden"],
            },
        ],
        "ghi_chu": (
            "Hệ thống hiện phân quyền theo 1 vai trò (role) JWT mỗi người dùng "
            "— CHƯA có ma trận quyền chi tiết theo từng nghiệp vụ (xem/ghi sổ/"
            "khoá sổ/xem lương…) như thiết kế ban đầu đề xuất. Đổi vai trò của "
            "một người ở màn Nhân sự (HCNS)."
        ),
    }


# ─── GET — cả 5 tab ──────────────────────────────────────────────────────

@router.get("/api/cai-dat")
def get_cai_dat(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    dv = get_or_seed_don_vi(db)
    st = _get_or_seed_settings(db)
    ke_toan = _ke_toan_to_dict(st)
    if not ke_toan["ngay_bat_dau_dung"]:
        # Chưa khai báo → lấy ngày chứng từ sớm nhất trong sổ (số liệu thật).
        dau = db.execute(select(func.min(JournalEntry.ngay))).scalar()
        ke_toan["ngay_bat_dau_dung"] = dau.isoformat() if dau else None
    return {
        # FE khoá ô nhập + ẩn nút Lưu khi False — PUT cũng chặn 403 ở server.
        "quyen_sua": user.role in _CEO_THUCHI_ROLES,
        "don_vi": don_vi_to_dict(dv),
        "ke_toan": ke_toan,
        "khoa_so_den": _khoa_so_den(db),
        "duyet_chi": _duyet_chi_info(),
        "danh_so": st.danh_so or [],
        "phan_quyen": _phan_quyen_info(db),
    }


# ─── PUT đơn vị ──────────────────────────────────────────────────────────

@router.put("/api/cai-dat/don_vi")
def put_don_vi(
    body: DonViIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _EDIT_AUTH],
):
    dv = get_or_seed_don_vi(db)
    for k, v in body.model_dump().items():
        setattr(dv, k, v)
    dv.updated_by = user.username
    db.commit()
    db.refresh(dv)
    log_action(
        db, app="ketoan", action="cai_dat_don_vi_update", user=user, request=request,
        resource="ketoan.don_vi:1", payload=body.model_dump(),
    )
    return don_vi_to_dict(dv)


# ─── PUT chính sách kế toán ──────────────────────────────────────────────

@router.put("/api/cai-dat/ke_toan")
def put_ke_toan(
    body: KeToanSettingsIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _EDIT_AUTH],
):
    st = _get_or_seed_settings(db)
    st.che_do = body.che_do
    st.nam_tc_bat_dau = body.nam_tc_bat_dau
    st.tien_te = body.tien_te or st.tien_te
    st.ngay_bat_dau_dung = body.ngay_bat_dau_dung
    st.gia_xuat_kho = body.gia_xuat_kho
    st.khau_hao = body.khau_hao
    st.ky_ke_khai_thue = body.ky_ke_khai_thue
    st.updated_by = user.username
    db.commit()
    db.refresh(st)
    log_action(
        db, app="ketoan", action="cai_dat_ke_toan_update", user=user, request=request,
        resource="ketoan.cai_dat_he_thong:1", payload=body.model_dump(mode="json"),
    )
    return _ke_toan_to_dict(st)


# ─── PUT đánh số chứng từ ────────────────────────────────────────────────

@router.put("/api/cai-dat/danh_so")
def put_danh_so(
    body: list[DanhSoRuleIn],
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _EDIT_AUTH],
):
    if not body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Danh sách quy tắc đánh số rỗng")
    seen: set[str] = set()
    for r in body:
        if r.ma in seen:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Trùng loại chứng từ: {r.ma}")
        seen.add(r.ma)

    st = _get_or_seed_settings(db)
    st.danh_so = [r.model_dump() for r in body]
    st.updated_by = user.username
    db.commit()
    db.refresh(st)
    log_action(
        db, app="ketoan", action="cai_dat_danh_so_update", user=user, request=request,
        resource="ketoan.cai_dat_he_thong:danh_so", payload={"so_dong": len(body)},
    )
    return st.danh_so


# ─── PUT duyệt chi / phân quyền — CHỈ ĐỌC (xem docstring module) ────────

@router.put("/api/cai-dat/duyet_chi")
def put_duyet_chi_readonly(user: Annotated[JWTPayload, _EDIT_AUTH]):
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        "Mục Duyệt chi chỉ hiển thị cấu hình phân quyền THẬT của hệ thống "
        "(vai trò + phòng/app) — chưa hỗ trợ đổi ngưỡng số tiền hay chọn "
        "người duyệt theo tên qua giao diện này.",
    )


@router.put("/api/cai-dat/phan_quyen")
def put_phan_quyen_readonly(user: Annotated[JWTPayload, _EDIT_AUTH]):
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        "Phân quyền hiện theo vai trò JWT toàn hệ thống (shared.users.role) — "
        "chưa hỗ trợ tạo vai trò tuỳ chỉnh hay gán quyền chi tiết qua giao "
        "diện này. Đổi vai trò của một người ở màn Nhân sự (HCNS).",
    )
