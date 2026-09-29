"""Tạm ứng nhân viên (TK 141) — API thật cho màn /ketoan/tam-ung (2026-09-25).

Endpoints (router không prefix — đường dẫn đầy đủ):
    GET    /api/tam-ung                       -- danh sách + thẻ số + đối chiếu sổ cái 141
    GET    /api/tam-ung/nhan-vien             -- nhân viên đang làm (ô chọn khi lập)
    GET    /api/tam-ung/{id}                  -- chi tiết + các lần quyết toán
    POST   /api/tam-ung                       -- lập phiếu chi tạm ứng (Nợ 141 / Có 111|112 + sổ quỹ)
    PUT    /api/tam-ung/{id}                  -- sửa (chỉ khi chưa quyết toán)        [CEO]
    DELETE /api/tam-ung/{id}                  -- xoá = đảo bút toán + xoá sổ quỹ       [CEO]
    POST   /api/tam-ung/quyet-toan            -- quyết toán (chi phí / hoàn / chi bù)
    POST   /api/tam-ung/quyet-toan/{qt}/huy   -- huỷ lần quyết toán gần nhất           [CEO]

Quyền: xem + lập mới + quyết toán = mọi role Kế toán (require_ketoan_user);
sửa/xoá/huỷ = CEO/admin/trợ lý CEO (require_ceo_thuchi) — cùng quy tắc kiểm
soát nội bộ với lệnh thu-chi khác (routers/_deps.py).
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..schemas.tam_ung import QuyetToanIn, TamUngIn
from ..services import tam_ung as svc
from ._deps import _CEO_THUCHI_ROLES, require_ceo_thuchi, require_ketoan_user

router = APIRouter()
_Db = Annotated[Session, Depends(get_db)]
_User = Annotated[JWTPayload, Depends(require_ketoan_user)]
_Ceo = Annotated[JWTPayload, Depends(require_ceo_thuchi)]


def _bust_pl_cache() -> None:
    try:
        from .bao_cao_pnl import invalidate_pl_cache
        invalidate_pl_cache()
    except Exception:
        pass


def _log(db: Session, action: str, user: JWTPayload, request: Request, rid, payload: dict) -> None:
    log_action(db, app="ketoan", action=action, user=user, request=request,
               resource=f"tam_ung:{rid}", payload=payload)


@router.get("/api/tam-ung")
def list_tam_ung(
    db: _Db, user: _User,
    tim: str = Query("", max_length=100),
    trang_thai: str = Query("", max_length=30),
):
    out = svc.list_tam_ung(db, tim, trang_thai)
    out["quyen_sua"] = user.role in _CEO_THUCHI_ROLES
    return out


@router.get("/api/tam-ung/nhan-vien")
def list_nhan_vien(db: _Db, user: _User):
    return svc.list_nhan_vien(db)


@router.get("/api/tam-ung/{tu_id}")
def get_tam_ung(tu_id: int, db: _Db, user: _User):
    return svc.get_tam_ung(db, tu_id)


@router.post("/api/tam-ung", status_code=201)
def create_tam_ung(body: TamUngIn, request: Request, db: _Db, user: _User):
    tu = svc.tao_tam_ung(db, body, user.username)
    _log(db, "create_tam_ung", user, request, tu.id,
         {"so_ct": tu.so_ct, "nhan_vien": tu.nhan_vien_ma, "so_tien": str(tu.so_tien)})
    return svc.serialize(tu, chi_tiet=True)


@router.put("/api/tam-ung/{tu_id}")
def update_tam_ung(tu_id: int, body: TamUngIn, request: Request, db: _Db, user: _Ceo):
    tu = svc.sua_tam_ung(db, tu_id, body, user.username)
    _log(db, "update_tam_ung", user, request, tu.id,
         {"so_ct": tu.so_ct, "nhan_vien": tu.nhan_vien_ma, "so_tien": str(tu.so_tien)})
    return svc.serialize(tu, chi_tiet=True)


@router.delete("/api/tam-ung/{tu_id}")
def delete_tam_ung(tu_id: int, request: Request, db: _Db, user: _Ceo):
    tu = svc.xoa_tam_ung(db, tu_id, user.username)
    _log(db, "delete_tam_ung", user, request, tu.id, {"so_ct": tu.so_ct})
    return {"ok": True, "so_ct": tu.so_ct}


@router.post("/api/tam-ung/quyet-toan")
def quyet_toan(body: QuyetToanIn, request: Request, db: _Db, user: _User):
    out = svc.quyet_toan(db, body, user.username)
    _bust_pl_cache()
    _log(db, "quyet_toan_tam_ung", user, request, body.id,
         {"so_ct": out["so_ct"], "chi_phi": str(body.chi_phi), "tk_cp": body.tk_cp})
    return out


@router.post("/api/tam-ung/quyet-toan/{qt_id}/huy")
def huy_quyet_toan(qt_id: int, request: Request, db: _Db, user: _Ceo):
    tu = svc.huy_quyet_toan(db, qt_id, user.username)
    _bust_pl_cache()
    _log(db, "huy_quyet_toan_tam_ung", user, request, tu.id, {"qt_id": qt_id})
    return svc.serialize(tu, chi_tiet=True)
