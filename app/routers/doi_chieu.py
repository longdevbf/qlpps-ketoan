"""Cảnh báo kỳ + đối chiếu sổ cái ↔ bảng nghiệp vụ — Đợt 1, 07/10/2026. CHỈ ĐỌC.

Endpoints (prefix /api/bao-cao, khai ở app/main.py):
    GET /api/bao-cao/canh-bao?thang=YYYY-MM   cảnh báo hiện đầu 3 báo cáo + màn đối chiếu
    GET /api/bao-cao/doi-chieu?thang=YYYY-MM  từng khoản mục: số sổ cái, số bảng nghiệp vụ, chênh

Không endpoint nào ở đây ghi DB → không có log_action (audit chỉ cho thao tác ghi/sửa/xoá).
"""
from datetime import date as date_cls
from decimal import Decimal
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from shared.auth import JWTPayload
from shared.db import get_db

from ..schemas.doi_chieu import CanhBaoOut, DoiChieuOut
from ..services.canh_bao_ky import ky_chua_chot, lech_can_doi, thieu_khau_hao, von_gop_chua_khai
from ..services.doi_chieu_so import doi_chieu_kqkd, phat_sinh_theo_tk
from ..services.loi_doc import bat_dau_ghi_loi
from ..services.nguon_bao_cao import NHAN_CDKT
from ..services.pl_calculator import calc_pl_for_month
from ._deps import require_ketoan_user
from .bao_cao_can_doi import _resolve_thang, bao_cao_can_doi

router = APIRouter()
_AUTH = Depends(require_ketoan_user)


def _dong(x) -> Optional[Decimal]:
    """Số Cân đối (float, kế thừa từ báo cáo cũ) → Decimal làm tròn 2 số lẻ — để JSON không ra
    chuỗi kiểu "0.30000000000000004" khi Pydantic chuyển float sang Decimal."""
    return None if x is None else Decimal(str(round(float(x), 2)))


@router.get("/canh-bao", response_model=CanhBaoOut)
def canh_bao_ky(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    thang: Optional[str] = Query(None, description="YYYY-MM (mặc định tháng hiện tại)"),
    man: Optional[Literal["cdkt", "kqkd", "lctt", "doi_chieu"]] = Query(
        None, description="Màn đang hỏi — KQKD/LCTT không cần cảnh báo của Cân đối nên khỏi tính Cân đối"),
):
    """Những điều làm số của kỳ `thang` chưa đáng tin: lệch cân đối, vốn góp chưa khai, kỳ chưa
    chốt, tháng chưa chạy khấu hao, bảng không đọc được. Rỗng = không phát hiện gì."""
    thang, _tu, _den = _resolve_thang(thang)
    hien_tai = date_cls.today().strftime("%Y-%m")
    if man in ("kqkd", "lctt"):
        # Lệch cân đối / vốn góp chỉ hiện ở màn Cân đối + Đối chiếu → khỏi tính cả Cân đối cho mỗi lần mở KQKD/LCTT.
        loi_doc = bat_dau_ghi_loi()
        chung = ky_chua_chot(db, thang, hien_tai) + thieu_khau_hao(db, thang, hien_tai)
        return {"thang": thang, "canh_bao": chung, "loi_doc_du_lieu": loi_doc}
    # Cân đối TRƯỚC: bao_cao_can_doi mở danh sách lỗi đọc (ContextVar, app/services/loi_doc.py) — các
    # hàm gọi SAU ghi tiếp vào đúng danh sách đó. Gọi ky_chua_chot trước thì lỗi đọc của nó rơi vào
    # khoảng chưa có danh sách: chỉ ghi log, không tới màn hình.
    bc = bao_cao_can_doi(db, user, thang=thang, source="auto")
    chung = ky_chua_chot(db, thang, hien_tai) + thieu_khau_hao(db, thang, hien_tai)
    rieng = von_gop_chua_khai(bc) + chung
    # Ý nào đã hiện ở chỗ khác trên cùng màn thì bỏ khỏi danh sách nguyên nhân của khối đỏ "lệch cân
    # đối" — cùng một ý không nói hai lần. Mã là mã trong check.nguyen_nhan của bao_cao_can_doi.
    co = {x["ma"] for x in rieng}
    bo_ma: set[str] = set()        # đã có cảnh báo riêng (kèm nút tới màn xử lý)
    if "von_gop_chua_khai" in co:
        bo_ma.add("von_gop_chua_khai")
    if "ky_chua_chot" in co:
        bo_ma.add("chua_chot_ky")
    bo_ma_bang: set[str] = set()   # đã hiện ở bảng ngay dưới
    if man == "doi_chieu":
        bo_ma_bang.add("so_cai_khac_nghiep_vu")   # màn Đối chiếu tô vàng đúng các khoản mục này
    ds = lech_can_doi(bc, frozenset(bo_ma), frozenset(bo_ma_bang)) + rieng
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
         "so_cai": _dong(v.get("so_cai")), "nghiep_vu": _dong(v.get("nghiep_vu")), "chenh": _dong(v.get("chenh")),
         "dang_dung": v.get("dang_dung", "khac")}
        for k, v in bc["nguon"].items() if k in NHAN_CDKT
    ]
    pl = calc_pl_for_month(db, thang)
    kqkd = doi_chieu_kqkd(pl, phat_sinh_theo_tk(db, tu, den))
    return {
        "thang": thang, "tu_ngay": tu.isoformat(), "den_ngay": den.isoformat(),
        # Cùng một danh sách (ContextVar) nên gồm cả lỗi đọc của bước tính KQKD phía trên.
        "can_doi": can_doi, "kqkd": kqkd, "loi_doc_du_lieu": bc.get("loi_doc_du_lieu") or [],
    }
