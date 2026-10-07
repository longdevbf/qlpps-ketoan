"""Cảnh báo kỳ + đối chiếu sổ cái ↔ bảng nghiệp vụ — Đợt 1, 07/10/2026. CHỈ ĐỌC.

Endpoints (prefix /api/bao-cao, khai ở app/main.py):
    GET /api/bao-cao/canh-bao?thang=YYYY-MM   cảnh báo hiện đầu 3 báo cáo + màn đối chiếu
    GET /api/bao-cao/doi-chieu?thang=YYYY-MM  từng khoản mục: số sổ cái, số bảng nghiệp vụ, chênh

Không endpoint nào ở đây ghi DB → không có log_action (audit chỉ cho thao tác ghi/sửa/xoá).
"""
from datetime import date as date_cls
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from shared.auth import JWTPayload
from shared.db import get_db

from ..schemas.doi_chieu import CanhBaoOut, DoiChieuOut
from ..services.canh_bao_ky import ky_chua_chot, lech_can_doi, thieu_khau_hao, von_gop_chua_khai
from ..services.doi_chieu_so import doi_chieu_kqkd, phat_sinh_theo_tk
from ..services.nguon_bao_cao import NHAN_CDKT
from ..services.pl_calculator import calc_pl_for_month
from ._deps import require_ketoan_user
from .bao_cao_can_doi import _resolve_thang, bao_cao_can_doi

router = APIRouter()
_AUTH = Depends(require_ketoan_user)


@router.get("/canh-bao", response_model=CanhBaoOut)
def canh_bao_ky(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    thang: Optional[str] = Query(None, description="YYYY-MM (mặc định tháng hiện tại)"),
):
    """Những điều làm số của kỳ `thang` chưa đáng tin: lệch cân đối, vốn góp chưa khai, kỳ chưa
    chốt, tháng chưa chạy khấu hao, bảng không đọc được. Rỗng = không phát hiện gì."""
    thang, _tu, den = _resolve_thang(thang)
    hien_tai = date_cls.today().strftime("%Y-%m")
    bc = bao_cao_can_doi(db, user, thang=thang, source="auto")
    ds = (
        lech_can_doi(bc)
        + von_gop_chua_khai(db, den)
        + ky_chua_chot(db, thang, hien_tai)
        + thieu_khau_hao(db, thang, hien_tai)
    )
    return {"thang": thang, "canh_bao": ds, "loi_doc_du_lieu": bc.get("loi_doc_du_lieu") or []}


@router.get("/doi-chieu", response_model=DoiChieuOut)
def doi_chieu_so_cai_nghiep_vu(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    thang: Optional[str] = Query(None, description="YYYY-MM (mặc định tháng hiện tại)"),
):
    """Mỗi khoản mục: số theo sổ cái, số theo bảng nghiệp vụ, phần chênh, và số báo cáo đang dùng.

    Cân đối: số dư cuối tháng (đọc lại từ /can-doi chế độ auto — cùng một lần tính, không tính lại).
    KQKD: phát sinh TK 5xx–8xx trong tháng (bỏ bút toán kết chuyển 911) ↔ dòng P&L của tháng.
    """
    thang, tu, den = _resolve_thang(thang)
    bc = bao_cao_can_doi(db, user, thang=thang, source="auto")
    can_doi = [
        {"khoa": k, "nhan": NHAN_CDKT[k], "tk": v["tk"], "bang": v.get("bang"),
         "so_cai": v.get("so_cai"), "nghiep_vu": v.get("nghiep_vu"), "chenh": v.get("chenh"),
         "dang_dung": v.get("dang_dung", "khac")}
        for k, v in bc["nguon"].items() if k in NHAN_CDKT
    ]
    pl = calc_pl_for_month(db, thang)
    kqkd = doi_chieu_kqkd(pl, phat_sinh_theo_tk(db, tu, den))
    for r in kqkd:
        r["bang"] = "Kết quả kinh doanh (bảng nghiệp vụ)"
    return {
        "thang": thang, "tu_ngay": tu.isoformat(), "den_ngay": den.isoformat(),
        # Cùng một danh sách (ContextVar) nên gồm cả lỗi đọc của bước tính KQKD phía trên.
        "can_doi": can_doi, "kqkd": kqkd, "loi_doc_du_lieu": bc.get("loi_doc_du_lieu") or [],
    }
