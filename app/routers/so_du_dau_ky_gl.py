"""Số dư đầu kỳ theo hệ thống tài khoản kế toán — API thật cho /ketoan/so-du-dau-ky.

KHÔNG dùng /api/so-du-dau-ky: đường đó đã là số dư đầu tháng TK ngân hàng
(routers/so_du_dau_ky.py, màn Sổ quỹ/Ngân hàng đang dùng).

Endpoints (router không prefix — đường dẫn đầy đủ):
    GET /api/so-du-dau-ky-gl                  -- số dư từng TK loại 1–4 (tiền theo TK con 1111, 1121…) + chi tiết đối tượng
    GET /api/so-du-dau-ky-gl/doi-tuong        -- tìm khách hàng/NCC/nhân viên (?tk=131&q=)
    PUT /api/so-du-dau-ky-gl                  -- lưu (thay toàn bộ)                    [CEO]

Lưu = một bút toán journal source_type='so_du_dau_ky' (xem services/so_du_dau_ky_gl.py).
Sửa yêu cầu CEO/admin/trợ lý CEO (require_ceo_thuchi) — cùng mức với cài đặt kế
toán và bút toán tay (ghi thẳng vốn/tiền).
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..schemas.so_du_dau_ky_gl import SoDuDauKyIn
from ..services import so_du_dau_ky_gl as svc
from ._deps import _CEO_THUCHI_ROLES, require_ceo_thuchi, require_ketoan_user

router = APIRouter()
_Db = Annotated[Session, Depends(get_db)]
_User = Annotated[JWTPayload, Depends(require_ketoan_user)]
_Ceo = Annotated[JWTPayload, Depends(require_ceo_thuchi)]


@router.get("/api/so-du-dau-ky-gl")
def get_so_du(db: _Db, user: _User):
    return svc.doc_so_du(db, quyen_sua=user.role in _CEO_THUCHI_ROLES)


@router.get("/api/so-du-dau-ky-gl/doi-tuong")
def tim_doi_tuong(
    db: _Db, user: _User,
    tk: str = Query(..., max_length=10),
    q: str = Query("", max_length=100),
):
    return svc.tim_doi_tuong(db, tk, q)


@router.put("/api/so-du-dau-ky-gl")
def put_so_du(body: SoDuDauKyIn, request: Request, db: _Db, user: _Ceo):
    out = svc.luu_so_du(db, body, user.username)
    log_action(db, app="ketoan", action="luu_so_du_dau_ky_gl", user=user, request=request,
               resource=f"journal_entry:{out['but_toan_id']}", payload=out)
    return out
