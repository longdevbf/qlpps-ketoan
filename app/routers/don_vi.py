"""Đơn vị kế toán — thông tin công ty in trên đầu chứng từ/báo cáo (letterhead).

    GET  /api/don-vi   -- dùng bởi trang in `/ketoan/in` (kt-in.js) VÀ tab
                           "Đơn vị" của màn Cài đặt (`/api/cai-dat`, xem
                           app/routers/cai_dat.py — đọc lại cùng 1 bảng).

Trước 2026-09-25, endpoint này không tồn tại → trang in luôn báo lỗi. Dữ liệu
lưu tại bảng singleton `ketoan.don_vi` (đúng 1 dòng, id=1), sửa qua
PUT /api/cai-dat/don_vi (chỉ CEO/admin/trợ lý CEO — anh Quang 2026-09-25).
"""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.auth import JWTPayload
from shared.db import get_db
from shared.models import User

from ..models.don_vi import DonVi
from ._deps import require_ketoan_user

router = APIRouter()
_AUTH = Depends(require_ketoan_user)


def get_or_seed_don_vi(db: Session) -> DonVi:
    """Đọc dòng đơn vị duy nhất; nếu bảng vừa tạo mà chưa kịp seed (lifespan
    lỗi/race) thì tự tạo dòng rỗng — không bao giờ để GET 500 vì thiếu dữ liệu."""
    dv = db.get(DonVi, 1)
    if dv is None:
        dv = DonVi(id=1)
        db.add(dv)
        db.commit()
        db.refresh(dv)
    return dv


def don_vi_to_dict(dv: DonVi) -> dict:
    return {
        "ten": dv.ten,
        "ten_ngan": dv.ten_ngan,
        "mst": dv.mst,
        "dien_thoai": dv.dien_thoai,
        "dia_chi": dv.dia_chi,
        "email": dv.email,
        "giam_doc": dv.giam_doc,
        "ke_toan_truong": dv.ke_toan_truong,
        "thu_quy": dv.thu_quy,
        # trang in ký "Ngày ... tháng ... năm ..." theo hôm nay — không phải
        # cột lưu trong bảng (README 4.26: dv.hom_nay).
        "hom_nay": date.today().isoformat(),
    }


@router.get("/api/don-vi")
def get_don_vi(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    return don_vi_to_dict(get_or_seed_don_vi(db))


@router.get("/api/don-vi/ho-ten")
def get_ho_ten(
    username: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Họ tên in ở ô "Người lập" — chứng từ chỉ lưu username (created_by)."""
    ten = db.execute(
        select(User.full_name).where(User.username == username)
    ).scalar()
    return {"username": username, "ho_ten": ten or username}
