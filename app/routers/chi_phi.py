"""ChiPhiPhatSinh API — CRUD + phân nhóm chi phí + báo cáo gộp by-nhom.

Sprint M3 (2026-04-28): thêm `nhom_chi_phi` để phục vụ P&L
(ban_hang | quan_ly | tai_chinh | khac).
"""
import re
from datetime import date as date_cls, datetime
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db
from shared.events import emit_event

from ..models import (
    ChiPhiCoDinh, ChiPhiPhatSinh, CongNo, LoaiChiPhi,
    TaiKhoanNH, TaiKhoanNHGiaoDich,
)
from ..schemas import ChiPhiCreate, ChiPhiOut, ChiPhiUpdate
from ..services.journal import post_journal
from ..services.tai_khoan_tien import tk_tien_cua
from ..services.thu_chi_chi_tiet import doc_de_xuat_cua_chi_phi
from ._deps import require_ketoan_user, require_ceo_thuchi


# Map nhom_chi_phi → account_code TT200 (chi phí — số dư bên Nợ)
_NHOM_TO_ACCOUNT = {
    "ban_hang": "641",
    "quan_ly": "642",
    "tai_chinh": "635",
    "khac": "811",
}


router = APIRouter()
_AUTH = Depends(require_ketoan_user)
_CEO_EDIT = Depends(require_ceo_thuchi)  # sửa/xoá chi phí → chỉ CEO


VALID_NHOM = {"ban_hang", "quan_ly", "tai_chinh", "khac"}


def _bust_pl_cache() -> None:
    """Xoá cache P&L khi chi phí đổi (PERF-05)."""
    try:
        from .bao_cao_pnl import invalidate_pl_cache
        invalidate_pl_cache()
    except Exception:
        pass


def _resolve_nhom(db: Session, loai: Optional[str], nhom: Optional[str]) -> str:
    """Nếu FE không truyền nhom, lookup nhom_default theo loai_chi_phi.ten.
    Fallback 'khac'."""
    if nhom and nhom in VALID_NHOM:
        return nhom
    if loai:
        row = db.execute(
            select(LoaiChiPhi.nhom_default).where(LoaiChiPhi.ten == loai)
        ).scalar_one_or_none()
        if row and row in VALID_NHOM:
            return row
    return "khac"


# ─── List / filter by nhom ───────────────────────────────────────────────────

def _nguon_chi_phi(obj) -> str:
    """Phân loại nguồn 1 chi phí: 'theo luồng' (tự sinh từ nút Chi / cầu nối) vs
    'KT tự nhập' (nhập tay) — anh Quang 2026-08-27."""
    if getattr(obj, "ref_dntt", None):
        return "Đề Nghị TT"
    gc = (getattr(obj, "ghi_chu", None) or "")
    if gc.startswith("Chi đề xuất"):
        return "Đề xuất chi"
    if getattr(obj, "ref_vc", None):
        return "Vận chuyển (auto)"
    if getattr(obj, "ref_ads_thang_kenh", None):
        return "Ads (auto)"
    # 'YYYY-MM' = kỳ lương KT chọn cho khoản Ứng Lương nhập tay (xem create_chi_phi), KHÔNG phải cầu nối
    # lương tự sinh 'PAYROLL-…' — trước 28/09/2026 bị gắn nhầm nhãn "Lương (auto)".
    _ref_luong = getattr(obj, "ref_payroll_thang_pb", None) or ""
    if _ref_luong and not re.match(r"^\d{4}-\d{2}$", _ref_luong):
        return "Lương (auto)"
    if getattr(obj, "ref_phatsinh", None):
        return "Phát sinh (auto)"
    return "KT tự nhập"


@router.get("", response_model=list[ChiPhiOut])
def list_chi_phi(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu_ngay: Optional[date_cls] = Query(None),
    den_ngay: Optional[date_cls] = Query(None),
    loai_chi_phi: Optional[str] = None,
    quy: Optional[str] = None,
    nhom: Optional[str] = Query(None, description="Filter nhom_chi_phi: ban_hang|quan_ly|tai_chinh|khac"),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = 0,
):
    stmt = select(ChiPhiPhatSinh).order_by(
        ChiPhiPhatSinh.ngay.desc(), ChiPhiPhatSinh.id.desc()
    )
    if tu_ngay:
        stmt = stmt.where(ChiPhiPhatSinh.ngay >= tu_ngay)
    if den_ngay:
        stmt = stmt.where(ChiPhiPhatSinh.ngay <= den_ngay)
    if loai_chi_phi:
        stmt = stmt.where(ChiPhiPhatSinh.loai_chi_phi == loai_chi_phi)
    if quy:
        stmt = stmt.where(ChiPhiPhatSinh.quy == quy)
    if nhom:
        if nhom not in VALID_NHOM:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"nhom phải thuộc {sorted(VALID_NHOM)}")
        stmt = stmt.where(ChiPhiPhatSinh.nhom_chi_phi == nhom)
    stmt = stmt.limit(limit).offset(offset)
    rows = db.execute(stmt).scalars().all()
    for r in rows:
        # gán nhãn nguồn (transient attr) để ChiPhiOut trả về FE hiển thị badge
        try:
            r.nguon = _nguon_chi_phi(r)
        except Exception:
            r.nguon = None
    return rows


# ─── /by-nhom: gộp theo nhom + nguồn (CP phát sinh + cố định + lương + ads) ─

@router.get("/by-nhom")
def chi_phi_by_nhom(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu: date_cls = Query(..., alias="from"),
    den: date_cls = Query(..., alias="to"),
):
    """Gộp chi phí theo nhóm (ban_hang/quan_ly/tai_chinh/khac) từ nhiều nguồn:

      - chi_phi_phat_sinh (group by nhom_chi_phi)
      - chi_phi_co_dinh   (group by nhom_chi_phi, chỉ tháng overlap)
      - hcns.payroll      (lương → ban_hang nếu phòng ban KD/MKT, ngược lại quan_ly)
      - marketing.ads_cost (toàn bộ → ban_hang)
      - ketoan.khoan_vay_giao_dich (lãi vay → tai_chinh)
    """
    if tu > den:
        tu, den = den, tu

    # Khởi tạo
    out = {n: {"total": 0.0, "sources": {}} for n in VALID_NHOM}

    # 1. chi_phi_phat_sinh
    rows = db.execute(
        select(
            ChiPhiPhatSinh.nhom_chi_phi,
            func.coalesce(func.sum(ChiPhiPhatSinh.so_tien), 0),
        )
        .where(ChiPhiPhatSinh.ngay >= tu, ChiPhiPhatSinh.ngay <= den)
        .group_by(ChiPhiPhatSinh.nhom_chi_phi)
    ).all()
    for nhom, total in rows:
        key = nhom if nhom in VALID_NHOM else "khac"
        v = float(total or 0)
        out[key]["sources"]["chi_phi_phat_sinh"] = (
            out[key]["sources"].get("chi_phi_phat_sinh", 0.0) + v
        )
        out[key]["total"] += v

    # 2. chi_phi_co_dinh — đếm tháng overlap
    months = _months_in_range(tu, den)
    if months:
        cd_rows = db.execute(
            select(
                ChiPhiCoDinh.nhom_chi_phi,
                ChiPhiCoDinh.thang_bat_dau,
                ChiPhiCoDinh.so_tien_thang,
                ChiPhiCoDinh.lap_lai,
            )
        ).all()
        for nhom, t_start, st, lap_lai in cd_rows:
            if not st or not t_start:
                continue
            start_ym = t_start.strftime("%Y-%m")
            if lap_lai:
                applicable = [m for m in months if m >= start_ym]
            else:
                applicable = [m for m in months if m == start_ym]
            if not applicable:
                continue
            v = float(st) * len(applicable)
            key = nhom if nhom in VALID_NHOM else "khac"
            out[key]["sources"]["chi_phi_co_dinh"] = (
                out[key]["sources"].get("chi_phi_co_dinh", 0.0) + v
            )
            out[key]["total"] += v

    # 3. Lương → ban_hang vs quan_ly theo phòng ban
    if months:
        ph = ",".join(f":m{i}" for i in range(len(months)))
        params: dict[str, Any] = {f"m{i}": v for i, v in enumerate(months)}
        sql_luong = f"""
            SELECT COALESCE(LOWER(e.phong_ban), '') AS pb,
                   COALESCE(SUM(p.thuc_linh), 0)
            FROM hcns.payroll p
            LEFT JOIN hcns.employees e ON e.id = p.employee_id
            WHERE p.thang IN ({ph})
            GROUP BY pb
        """
        try:
            rows_l = db.execute(text(sql_luong), params).all()
        except (ProgrammingError, OperationalError):
            db.rollback()
            rows_l = []
        BH_KEYS = ("kinh doanh", "kd", "sale", "marketing", "mkt")
        for pb, total in rows_l:
            v = float(total or 0)
            if any(k in (pb or "") for k in BH_KEYS):
                key = "ban_hang"
            else:
                key = "quan_ly"
            out[key]["sources"]["luong"] = out[key]["sources"].get("luong", 0.0) + v
            out[key]["total"] += v

    # 4. Ads marketing → toàn bộ ban_hang
    sql_ads = """
        SELECT COALESCE(SUM(chi_phi), 0)
        FROM marketing.ads_cost
        WHERE ngay >= :tu AND ngay <= :den
    """
    try:
        ads = float(db.execute(text(sql_ads), {"tu": tu, "den": den}).scalar() or 0)
    except (ProgrammingError, OperationalError):
        db.rollback()
        ads = 0.0
    if ads:
        out["ban_hang"]["sources"]["ads"] = out["ban_hang"]["sources"].get("ads", 0.0) + ads
        out["ban_hang"]["total"] += ads

    # 5. Lãi vay → tai_chinh
    sql_vay = """
        SELECT COALESCE(SUM(
            CASE
                WHEN gd.loai = 'tra_lai' THEN gd.so_tien
                WHEN gd.loai = 'tra_goc_lai' THEN COALESCE(gd.so_tien_lai, 0)
                ELSE 0
            END
        ), 0)
        FROM ketoan.khoan_vay_giao_dich gd
        WHERE gd.ngay >= :tu AND gd.ngay <= :den
    """
    try:
        lai = float(db.execute(text(sql_vay), {"tu": tu, "den": den}).scalar() or 0)
    except (ProgrammingError, OperationalError):
        db.rollback()
        lai = 0.0
    if lai:
        out["tai_chinh"]["sources"]["lai_vay"] = (
            out["tai_chinh"]["sources"].get("lai_vay", 0.0) + lai
        )
        out["tai_chinh"]["total"] += lai

    grand = sum(v["total"] for v in out.values())
    return {
        "from": str(tu), "to": str(den),
        "nhom": {k: {"total": round(v["total"], 2), "sources": {s: round(x, 2) for s, x in v["sources"].items()}} for k, v in out.items()},
        "grand_total": round(grand, 2),
    }


def _months_in_range(tu: date_cls, den: date_cls) -> list[str]:
    out: list[str] = []
    y, m = tu.year, tu.month
    while (y, m) <= (den.year, den.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


# ─── CRUD ────────────────────────────────────────────────────────────────────

@router.post("", response_model=ChiPhiOut, status_code=status.HTTP_201_CREATED)
def create_chi_phi(
    body: ChiPhiCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    fields = body.model_dump(exclude_unset=True)
    fields["nhom_chi_phi"] = _resolve_nhom(
        db, fields.get("loai_chi_phi"), fields.get("nhom_chi_phi"),
    )
    # Pop journal-only fields
    tai_khoan_id = fields.pop("tai_khoan_id", None)
    cong_no_ncc_id = fields.pop("cong_no_ncc_id", None)
    # Kỳ lương (Ứng Lương): 'YYYY-MM' → lưu cột ref_payroll_thang_pb để HCNS trừ đúng kỳ.
    _ky = fields.pop("ky_luong", None)
    if _ky and re.match(r"^\d{4}-\d{2}$", str(_ky)):
        fields["ref_payroll_thang_pb"] = str(_ky)

    # CHẶN chi phí làm số dư TK âm (anh Quang 2026-08-27)
    _tk_name = fields.get("ngan_hang")
    if not _tk_name and tai_khoan_id:
        _tk0 = db.get(TaiKhoanNH, tai_khoan_id)
        _tk_name = _tk0.ten_tk if _tk0 else None
    if _tk_name:
        from ..services.so_quy_auto import assert_du_chi
        assert_du_chi(db, _tk_name, fields.get("so_tien"))

    obj = ChiPhiPhatSinh(**fields, created_by=user.username)
    db.add(obj)
    db.flush()

    # Phase 2 — Double-entry posting
    nhom = obj.nhom_chi_phi or "khac"
    cp_account = _NHOM_TO_ACCOUNT.get(nhom, "811")

    if tai_khoan_id:
        tk = db.get(TaiKhoanNH, tai_khoan_id)
        if not tk:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"tai_khoan_id={tai_khoan_id} không tồn tại",
            )
        cash_acc = tk_tien_cua(tk)
        gd = TaiKhoanNHGiaoDich(
            ngay=obj.ngay, tai_khoan_id=tk.id, loai="chi",
            so_tien=obj.so_tien, doi_tac=obj.nguoi_chi,
            ghi_chu=f"Chi phí {obj.loai_chi_phi or ''} — {obj.mo_ta or ''}",
            source_app="chi_phi", source_doc_id=f"chi_phi_{obj.id}",
            created_by=user.username,
        )
        db.add(gd)
        db.flush()
        post_journal(
            db, ngay=obj.ngay,
            mo_ta=f"Chi phí {obj.loai_chi_phi or ''} — TT bằng {tk.ten_tk}",
            source_type="chi_phi_phat_sinh", source_id=str(obj.id),
            by_user=user.username,
            lines=[
                {"loai": "no", "account_code": cp_account,
                 "ref_table": "chi_phi_phat_sinh", "ref_id": obj.id,
                 "so_tien": obj.so_tien,
                 "ghi_chu": f"{nhom} — {obj.loai_chi_phi or ''}"},
                {"loai": "co", "account_code": cash_acc,
                 "ref_table": "tai_khoan_nh", "ref_id": tk.id,
                 "so_tien": obj.so_tien,
                 "ghi_chu": f"Chi từ {tk.ten_tk}"},
            ],
        )
    elif cong_no_ncc_id:
        cn = db.get(CongNo, cong_no_ncc_id)
        if not cn:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"cong_no_ncc_id={cong_no_ncc_id!r} không tồn tại",
            )
        post_journal(
            db, ngay=obj.ngay,
            mo_ta=f"Chi phí {obj.loai_chi_phi or ''} — ghi nhận chưa trả",
            source_type="chi_phi_phat_sinh", source_id=str(obj.id),
            by_user=user.username,
            lines=[
                {"loai": "no", "account_code": cp_account,
                 "ref_table": "chi_phi_phat_sinh", "ref_id": obj.id,
                 "so_tien": obj.so_tien,
                 "ghi_chu": f"{nhom} — {obj.loai_chi_phi or ''}"},
                {"loai": "co", "account_code": "331",
                 "ref_table": "cong_no", "ref_id": None,
                 "so_tien": obj.so_tien,
                 "ghi_chu": f"Phải trả NCC ({cn.id})"},
            ],
        )

    db.commit()
    db.refresh(obj)
    # Auto-create SoQuy chi — CHỈ khi chi bằng TIỀN THẬT.
    # Mua chịu (cong_no_ncc_id): Có 331, CHƯA xuất tiền → KHÔNG ghi sổ quỹ ở đây
    # (nếu ghi sẽ trừ tiền ngay + trừ lần 2 khi trả NCC → double). Sổ quỹ chỉ lên
    # khi trả công nợ thật (tra_cong_no). (anh Quang 2026-08-28, LOG-01)
    if not cong_no_ncc_id:
        try:
            from ..services.so_quy_auto import sync_so_quy_from_chi_phi
            sync_so_quy_from_chi_phi(db, obj)
        except Exception:
            import logging
            logging.getLogger("ketoan.chi_phi").error(
                "sync_so_quy_from_chi_phi failed for chi_phi %s", obj.id, exc_info=True)
    _bust_pl_cache()
    log_action(
        db, app="ketoan", action="create_chi_phi", user=user, request=request,
        resource=f"chi_phi:{obj.id}",
        payload={"ngay": str(obj.ngay), "so_tien": str(obj.so_tien),
                 "loai": obj.loai_chi_phi, "nhom": obj.nhom_chi_phi,
                 "tai_khoan_id": tai_khoan_id,
                 "cong_no_ncc_id": cong_no_ncc_id},
    )
    emit_event("cost:new", {
        "id": obj.id, "ngay": str(obj.ngay) if obj.ngay else None,
        "so_tien": float(obj.so_tien or 0), "loai": obj.loai_chi_phi,
        "nhom": obj.nhom_chi_phi,
    })
    return obj


@router.get("/{rid}", response_model=ChiPhiOut)
def get_chi_phi(
    rid: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(ChiPhiPhatSinh, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ChiPhi không tồn tại")
    return obj


# ─── Chi tiết cho popup màn Thu chi ──────────────────────────────────────────
# Hai schema chỉ dùng cho endpoint dưới nên khai ngay tại đây (cùng kiểu de_nghi_tt.py).

class DeXuatChiNguon(BaseModel):
    """Đề xuất chi (shared.expense_requests) đã sinh ra dòng chi phí qua nút Chi — nơi có người nhận tiền."""
    id: int
    tieu_de: Optional[str] = None
    ho_ten: Optional[str] = None                 # người đề xuất
    phong_ban: Optional[str] = None
    ngay_de_xuat: Optional[date_cls] = None
    nguoi_thu_huong: Optional[str] = None        # người / đơn vị NHẬN tiền
    so_tk_nhan: Optional[str] = None
    ngan_hang_nhan: Optional[str] = None
    hinh_thuc: Optional[str] = None              # 'ck' | 'tm' — giao diện đổi sang nhãn
    ma_don: Optional[str] = None
    loai_chi_phi: Optional[str] = None
    chung_tu_urls: list[str] = []
    ho_ten_nguoi_duyet: Optional[str] = None
    ngay_duyet: Optional[datetime] = None


class ChiPhiChiTietOut(ChiPhiOut):
    """Đủ 23 cột của chi_phi_phat_sinh (thêm 3 khoá cầu nối ChiPhiOut chưa trả) + đề xuất chi nguồn."""
    ref_ads_thang_kenh: Optional[str] = None
    ref_phatsinh: Optional[str] = None
    ref_dntt: Optional[str] = None
    de_xuat: Optional[DeXuatChiNguon] = None
    # False = không đọc được shared.expense_requests trên máy này → giao diện báo "chưa đọc được".
    de_xuat_doc_duoc: bool = True


@router.get("/{rid}/chi-tiet", response_model=ChiPhiChiTietOut)
def chi_tiet_chi_phi(
    rid: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Popup chi tiết một dòng chi phí: mọi cột + người nhận tiền từ đề xuất chi, trong một lần gọi."""
    obj = db.get(ChiPhiPhatSinh, rid)
    if not obj:
        # Câu này hiện thẳng trong khối lỗi của popup → nói bằng chữ người đọc, không dùng tên class.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Không tìm thấy chi phí CP-{rid} — có thể vừa bị xoá, tải lại danh sách.",
        )
    obj.nguon = _nguon_chi_phi(obj)
    # Chụp dữ liệu ra dict TRƯỚC khi đọc chéo app: đọc lỗi thì savepoint bị huỷ,
    # không kéo theo đối tượng ORM.
    du_lieu = ChiPhiChiTietOut.model_validate(obj).model_dump()
    du_lieu["de_xuat"], du_lieu["de_xuat_doc_duoc"] = doc_de_xuat_cua_chi_phi(db, rid)
    return du_lieu


@router.put("/{rid}", response_model=ChiPhiOut)
def update_chi_phi(
    rid: int,
    body: ChiPhiUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _CEO_EDIT],
):
    obj = db.get(ChiPhiPhatSinh, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ChiPhi không tồn tại")
    fields = body.model_dump(exclude_unset=True)
    # Nếu user đổi loai_chi_phi mà không truyền nhom → re-resolve theo loai mới
    if "loai_chi_phi" in fields and "nhom_chi_phi" not in fields:
        fields["nhom_chi_phi"] = _resolve_nhom(db, fields["loai_chi_phi"], None)
    if "nhom_chi_phi" in fields and fields["nhom_chi_phi"] not in VALID_NHOM:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"nhom_chi_phi phải thuộc {sorted(VALID_NHOM)}"
        )
    # Kỳ lương (Ứng Lương) → cột ref_payroll_thang_pb ('YYYY-MM'); rỗng = xoá kỳ.
    if "ky_luong" in fields:
        _ky = fields.pop("ky_luong")
        obj.ref_payroll_thang_pb = str(_ky) if (_ky and re.match(r"^\d{4}-\d{2}$", str(_ky))) else None
    for k, v in fields.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    # Sync SoQuy — CHỈ khi chi phí này ĐÃ có dòng sổ quỹ (tức chi bằng tiền thật).
    # Chi phí MUA CHỊU (Có 331) lúc tạo KHÔNG ghi sổ quỹ (LOG-01); nếu ở đây gọi
    # sync vô điều kiện sẽ TẠO MỚI dòng chi → trừ tiền + trừ lần 2 khi trả NCC.
    # ChiPhiPhatSinh không có cột cong_no_ncc_id nên nhận diện bằng: đã tồn tại
    # SoQuy CP-{id} chưa. (L1, anh Quang 2026-08-31)
    try:
        from ..services.so_quy_auto import sync_so_quy_from_chi_phi
        from ..models import SoQuy as _SoQuy
        _existed = db.execute(
            select(_SoQuy.id).where(_SoQuy.lien_quan == "chi_phi", _SoQuy.ref_id == f"CP-{obj.id}")
        ).first()
        if _existed:
            sync_so_quy_from_chi_phi(db, obj)
    except Exception:
        import logging
        logging.getLogger("ketoan.chi_phi").warning("update sync so_quy failed cp=%s", obj.id, exc_info=True)
    _bust_pl_cache()
    log_action(
        db, app="ketoan", action="update_chi_phi", user=user, request=request,
        resource=f"chi_phi:{rid}", payload=fields,
    )
    return obj


@router.patch("/{rid}/nhom", response_model=ChiPhiOut)
def patch_nhom_chi_phi(
    rid: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _CEO_EDIT],
    nhom: str = Body(..., embed=True, description="ban_hang|quan_ly|tai_chinh|khac"),
):
    """Đổi nhanh `nhom_chi_phi` cho 1 row mà không cần PUT toàn bộ."""
    if nhom not in VALID_NHOM:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"nhom phải thuộc {sorted(VALID_NHOM)}",
        )
    obj = db.get(ChiPhiPhatSinh, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ChiPhi không tồn tại")
    obj.nhom_chi_phi = nhom
    db.commit()
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="patch_nhom_chi_phi", user=user, request=request,
        resource=f"chi_phi:{rid}", payload={"nhom": nhom},
    )
    return obj


@router.delete("/{rid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chi_phi(
    rid: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _CEO_EDIT],
):
    obj = db.get(ChiPhiPhatSinh, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ChiPhi không tồn tại")
    db.delete(obj)
    db.commit()

    # Xoá SoQuy chi liên quan — fail-soft. Pattern giống delete_doanh_thu:
    # SoQuy được upsert lúc create_chi_phi qua (lien_quan='chi_phi', ref_id=f'CP-{id}').
    try:
        from ..models import SoQuy
        from sqlalchemy import delete as sql_delete
        db.execute(
            sql_delete(SoQuy).where(
                SoQuy.lien_quan == "chi_phi",
                SoQuy.ref_id == f"CP-{rid}",
            )
        )
        db.commit()
    except Exception:
        db.rollback()

    # Cleanup giao dịch tài khoản NH (nếu chi phí được trả qua TK NH lúc create)
    try:
        from ..models import TaiKhoanNHGiaoDich
        from sqlalchemy import delete as sql_delete
        db.execute(
            sql_delete(TaiKhoanNHGiaoDich).where(
                TaiKhoanNHGiaoDich.source_app == "chi_phi",
                TaiKhoanNHGiaoDich.source_doc_id == f"chi_phi_{rid}",
            )
        )
        db.commit()
    except Exception:
        db.rollback()

    _bust_pl_cache()
    log_action(
        db, app="ketoan", action="delete_chi_phi", user=user, request=request,
        resource=f"chi_phi:{rid}",
    )
