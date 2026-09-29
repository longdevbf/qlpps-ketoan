"""API màn Chi phí chờ phân bổ — TK 242 (/ketoan/phan-bo) — 2026-09-25.

Nghiệp vụ + nguồn số liệu: services/phan_bo_242.py (đọc thật `chi_phi_co_dinh` phân bổ nhiều
tháng, cùng công thức báo cáo KQKD). Path đầy đủ khai trong router → main.py chỉ cần
`app.include_router(phan_bo.router, tags=["phan_bo"])`.

    GET  /api/phan-bo?tim&loai&trang_thai
    GET  /api/phan-bo/{id}
    POST /api/phan-bo         {ten, loai, tong, so_ky, tk_cp, doi, ngay, bo_phan}
    POST /api/phan-bo/thang   {thang}          -- Nợ 641/642 / Có 242 phần tới hạn chưa lên sổ
Quyền: mọi role Kế toán tạo mới (cùng mức POST /api/co-dinh); sửa/xoá khoản vẫn ở màn Chi phí
cố định (chỉ CEO). Mọi thao tác ghi có audit log.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..schemas.thue_phan_bo import PhanBoIn, ThangIn
from ..services import phan_bo_242
from ..services.thue_phan_bo_schema import dam_bao_bang_mot_lan
from ._deps import require_ketoan_user

router = APIRouter()
_Db = Annotated[Session, Depends(get_db)]
_User = Annotated[JWTPayload, Depends(require_ketoan_user)]


def _pl_cache_cu() -> None:
    """Khoản mới đổi chi phí KQKD → xoá cache P&L (giống co_dinh.py)."""
    from .bao_cao_pnl import invalidate_pl_cache
    invalidate_pl_cache()


@router.get("/api/phan-bo")
def danh_sach(
    db: _Db, user: _User,
    tim: str = Query("", max_length=100), loai: str = Query(""), trang_thai: str = Query(""),
):
    dam_bao_bang_mot_lan()
    return phan_bo_242.danh_sach(db, tim=tim, loai=loai, trang_thai=trang_thai)


@router.post("/api/phan-bo/thang")
def phan_bo_thang(body: ThangIn, request: Request, db: _Db, user: _User):
    dam_bao_bang_mot_lan()
    kq = phan_bo_242.phan_bo_thang(db, user, body.thang)
    log_action(db, app="ketoan", action="phan_bo_242_thang", user=user, request=request,
               resource=f"journal_entry:{kq['id']}", payload={"thang": body.thang, **kq})
    return kq


@router.get("/api/phan-bo/{cpcd_id}")
def chi_tiet(cpcd_id: int, db: _Db, user: _User):
    dam_bao_bang_mot_lan()
    return phan_bo_242.chi_tiet(db, cpcd_id)


@router.post("/api/phan-bo", status_code=status.HTTP_201_CREATED)
def them(body: PhanBoIn, request: Request, db: _Db, user: _User):
    dam_bao_bang_mot_lan()
    kq = phan_bo_242.them_khoan(db, user, body.model_dump())
    _pl_cache_cu()
    log_action(db, app="ketoan", action="phan_bo_242_them", user=user, request=request,
               resource=f"co_dinh:{kq['id']}", payload={**body.model_dump(mode="json"), **kq})
    return kq
