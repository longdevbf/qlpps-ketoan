"""API màn Thuế GTGT + Thuế TNCN/TNDN (/ketoan/thue-gtgt, /ketoan/thue-tncn-tndn) — 2026-09-25.

Trước đó 2 màn chỉ có giao diện, chưa có backend. Logic + nguồn số liệu: services/thue_gtgt.py,
services/thue_tn.py. Path đầy đủ khai trong router (giống don_vi/cai_dat) → main.py chỉ cần
`app.include_router(thue.router, tags=["thue"])`.

    GET  /api/thue-gtgt?ky=YYYY-MM|Qn-YYYY&chieu=ban|mua&tim&page&size&sort
    GET  /api/thue-gtgt/to-khai?ky=              -- {ten_tep, noi_dung} XML số liệu 01/GTGT
    GET  /api/thue-tncn?thang=
    POST /api/thue-tncn/ghi-so   {thang}         -- Nợ 334 / Có 3335
    GET  /api/thue-tncn/xuat?thang=              -- CSV số liệu 05/KK-TNCN
    GET  /api/thue-tndn?quy=
    PUT  /api/thue-tndn/dieu-chinh {quy, dong}   -- thay toàn bộ điều chỉnh của quý
    POST /api/thue-tndn/ghi-so   {quy}           -- Nợ 821 / Có 3334
Quyền: mọi role Kế toán (`require_ketoan_user`) — ghi sổ là TẠO bút toán mới từ số hệ thống tính,
cùng mức với chạy khấu hao tháng (tai_san.py). Mọi thao tác ghi đều có audit log.
"""
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..schemas.thue_phan_bo import DieuChinhIn, QuyIn, ThangIn
from ..services import thue_gtgt, thue_tn
from ..services.thue_phan_bo_schema import dam_bao_bang_mot_lan
from ._deps import require_ketoan_user
from .don_vi import get_or_seed_don_vi

router = APIRouter()
_Db = Annotated[Session, Depends(get_db)]
_User = Annotated[JWTPayload, Depends(require_ketoan_user)]


@router.get("/api/thue-gtgt")
def gtgt_danh_sach(
    db: _Db, user: _User,
    ky: str = Query(..., description="YYYY-MM hoặc Qn-YYYY"),
    chieu: Literal["ban", "mua"] = "ban",
    tim: str = Query("", max_length=100),
    dieu_kien: str = Query(""),
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=thue_gtgt.SIZE_TOI_DA),
    sort: str = Query("ngay_asc", max_length=30),
):
    return thue_gtgt.danh_sach(db, ky, chieu, tim=tim, page=page, size=size, sort=sort)


@router.get("/api/thue-gtgt/to-khai")
def gtgt_to_khai(db: _Db, user: _User, ky: str = Query(...)):
    dv = get_or_seed_don_vi(db)
    return thue_gtgt.to_khai_xml(db, ky, dv.mst, dv.ten)


@router.get("/api/thue-tncn")
def tncn(db: _Db, user: _User, thang: Optional[str] = Query(None)):
    return thue_tn.tncn_thang(db, user, thang)


@router.post("/api/thue-tncn/ghi-so")
def tncn_ghi_so(body: ThangIn, request: Request, db: _Db, user: _User):
    kq = thue_tn.ghi_so_tncn(db, user, body.thang)
    log_action(db, app="ketoan", action="thue_tncn_ghi_so", user=user, request=request,
               resource=f"journal_entry:{kq['id']}", payload={"thang": body.thang, **kq})
    return kq


@router.get("/api/thue-tncn/xuat")
def tncn_xuat(db: _Db, user: _User, thang: str = Query(...)):
    ten, noi_dung = thue_tn.xuat_tncn_csv(db, user, thang)
    return Response(noi_dung, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{ten}"'})


@router.get("/api/thue-tndn")
def tndn(db: _Db, user: _User, quy: Optional[str] = Query(None)):
    dam_bao_bang_mot_lan()
    return thue_tn.tndn_quy(db, quy)


@router.put("/api/thue-tndn/dieu-chinh")
def tndn_dieu_chinh(body: DieuChinhIn, request: Request, db: _Db, user: _User):
    dam_bao_bang_mot_lan()
    kq = thue_tn.luu_dieu_chinh(db, user, body.quy, [x.model_dump() for x in body.dong])
    log_action(db, app="ketoan", action="thue_tndn_dieu_chinh", user=user, request=request,
               resource=f"thue_tndn:{body.quy}", payload={"dong": [x.model_dump() for x in body.dong]})
    return kq


@router.post("/api/thue-tndn/ghi-so")
def tndn_ghi_so(body: QuyIn, request: Request, db: _Db, user: _User):
    dam_bao_bang_mot_lan()
    kq = thue_tn.ghi_so_tndn(db, user, body.quy)
    log_action(db, app="ketoan", action="thue_tndn_ghi_so", user=user, request=request,
               resource=f"journal_entry:{kq['id']}", payload={"quy": body.quy, **kq})
    return kq
