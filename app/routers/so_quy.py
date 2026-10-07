"""SoQuy API — auto-sync từ DoanhThu/ChiPhi/CongNo + chuyển nội bộ.

Anh chốt 2026-04-29: bỏ nhập tay sổ quỹ. Mọi entry sinh tự động qua hook
`so_quy_auto.py` từ 3 module nguồn. Riêng "chuyển nội bộ" giữa 2 TK có
endpoint riêng `POST /chuyen-noi-bo` (idempotent qua ref_id).

Manual CRUD vẫn giữ nhưng GATE chỉ admin/ceo/assistant_ceo (bỏ `manager`/`kt`).
"""
from datetime import date as date_cls, timedelta
from decimal import Decimal
from typing import Annotated, Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import SoQuy, TaiKhoanNH
from ..schemas import SoQuyCreate, SoQuyUpdate, SoQuyOut
from ..schemas.so_quy import NghiepVuDsOut, PhanLoaiCfOut, SoQuyTaoOut, TheoDonOut
from ..services import nghiep_vu_so_quy as nvsq
from ..services.phan_loai_cf import NHOM_TEN, danh_sach as ds_phan_loai_cf, khoa_dung_cho_loai
from ..services.so_quy_auto import so_du_truoc_ngay
from ._deps import require_ketoan_user, require_ceo_thuchi


router = APIRouter()
_AUTH = Depends(require_ketoan_user)
_CEO_EDIT = Depends(require_ceo_thuchi)  # sửa/xoá lệnh thu chi → chỉ CEO
# Kế Toán (`kt`) + Manager cũng được CRUD sổ quỹ tay (xoá entry orphan, sửa
# số phụ phí phát sinh ngoài luồng). admin/ceo/assistant_ceo giữ nguyên.
_ADMIN_ROLES = {"admin", "ceo", "assistant_ceo", "manager", "kt"}


def _require_admin(user: JWTPayload) -> None:
    """Manual CRUD sổ quỹ — admin/ceo/assistant_ceo/manager/kt được phép.
    Role thấp khác (kd/mkt/...) bị chặn vì không phải đối tượng dùng app này."""
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Sổ quỹ tự động sync từ Doanh Thu/Chi Phí/Công Nợ. "
            f"Role {user.role!r} không có quyền sửa tay.",
        )


def _lookup_nv_ten(db: Session, nv_id: Optional[int]) -> Optional[str]:
    """Auto-lookup ho_ten từ hcns.employees.

    hcns.employees PK = ma_nv (string vd 'NV26015'). Convert int 26015
    → 'NV%26015' để match qua ILIKE / suffix-match. Fail-soft trả None.
    """
    if not nv_id:
        return None
    try:
        # Match: ma_nv chứa cùng dãy số (vd 26015 → 'NV26015' / 'NV-26015' / 'NV_26015')
        row = db.execute(
            text(
                "SELECT ho_ten FROM hcns.employees "
                "WHERE regexp_replace(ma_nv, '\\D', '', 'g') = :digits "
                "LIMIT 1"
            ),
            {"digits": str(nv_id)},
        ).first()
        return row[0] if row else None
    except (ProgrammingError, OperationalError):
        db.rollback()
        return None


def _kiem_dong_tien(loai: Optional[str], cf: Optional[str]) -> None:
    """Mã dòng tiền phải hợp chiều phiếu. Lệch (vd phiếu THU gắn 'Trả NCC') thì dòng không lọt vào mục nào
    của báo cáo lưu chuyển tiền tệ — tiền biến mất khỏi báo cáo. NULL vẫn cho (bridge tự sinh không gắn mã)."""
    if not cf or not loai or khoa_dung_cho_loai(cf, loai):
        return
    raise HTTPException(
        422,
        f"Dòng tiền đã chọn không dùng cho phiếu {'thu' if loai == 'thu' else 'chi'}. "
        "Chọn lại dòng tiền đúng loại phiếu.",
    )


def _parse_thang(thang: Optional[str]) -> tuple[date_cls, date_cls]:
    """Trả (start_of_month, start_of_next_month). Default = current month."""
    today = date_cls.today()
    if not thang:
        y, m = today.year, today.month
    else:
        try:
            y_str, m_str = thang.split("-", 1)
            y, m = int(y_str), int(m_str)
        except (ValueError, AttributeError):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Tham số thang phải dạng YYYY-MM",
            )
    if not (1 <= m <= 12):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Tham số thang: tháng phải 1..12"
        )
    sm = date_cls(y, m, 1)
    em = date_cls(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
    return sm, em


@router.get("/summary")
def so_quy_summary(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    thang: Optional[str] = Query(None, description="YYYY-MM, default = current"),
    tu_ngay: Optional[date_cls] = Query(None, description="Kỳ tuỳ ý: từ ngày (gồm)"),
    den_ngay: Optional[date_cls] = Query(None, description="Kỳ tuỳ ý: đến ngày (gồm)"),
) -> dict[str, Any]:
    """Số dư từng tài khoản theo tháng (port từ V1 `/api/so-quy/summary`).

    Logic:
        so_du_dau_thang = tai_khoan_nh.so_du_dau + sum(SoQuy.thu - chi WHERE ngay < sm)
        thu = sum(SoQuy.so_tien WHERE loai='thu' AND sm <= ngay < em)
        chi = sum(SoQuy.so_tien WHERE loai='chi' AND sm <= ngay < em)
        so_du_cuoi = so_du_dau_thang + thu - chi

    Có `tu_ngay` + `den_ngay` (2026-09-25, màn Ngân hàng/Sổ quỹ lọc theo kỳ bất kỳ) →
    bỏ qua `thang`, tính trên [tu_ngay, den_ngay] (gồm 2 đầu); "so_du_dau_thang" khi
    đó là số dư NGAY TRƯỚC tu_ngay (`so_quy_auto.so_du_truoc_ngay`, cùng thuật toán neo).
    Không truyền → hành vi cũ theo tháng giữ nguyên (màn cũ /app#so-quy vẫn dùng).
    """
    if tu_ngay and den_ngay:
        if den_ngay < tu_ngay:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "den_ngay phải ≥ tu_ngay")
        sm, em = tu_ngay, den_ngay + timedelta(days=1)
    else:
        sm, em = _parse_thang(thang)

    tks = db.execute(
        select(TaiKhoanNH.id, TaiKhoanNH.ten_tk, TaiKhoanNH.so_du_dau, TaiKhoanNH.loai)
        .where(TaiKhoanNH.active.is_(True))
        .order_by(TaiKhoanNH.ten_tk)
    ).all()

    items: list[dict[str, Any]] = []
    tong_dau = tong_thu = tong_chi = tong_cuoi = Decimal("0")

    for tk in tks:
        # Anh Quang 2026-06-05: Số dư cuối kỳ tháng (X-1) = đầu kỳ tháng X — liên tục.
        # Thuật toán neo (anchor SoDuDauKy, forward/reverse/fallback) dùng chung với
        # màn Ngân Hàng qua so_quy_auto.so_du_truoc_ngay (= so_du_dau_ky khi `sm` là
        # ngày 1) — tách ra 2026-09-25 để 2 màn không tính lệch nhau khi lọc theo kỳ.
        so_du_dau_thang = so_du_truoc_ngay(db, tk.id, tk.ten_tk, sm)

        # Trong tháng
        thu_thang = db.scalar(
            select(func.coalesce(func.sum(SoQuy.so_tien), 0)).where(
                SoQuy.tai_khoan == tk.ten_tk,
                SoQuy.loai == "thu",
                SoQuy.ngay >= sm,
                SoQuy.ngay < em,
            )
        ) or Decimal("0")
        chi_thang = db.scalar(
            select(func.coalesce(func.sum(SoQuy.so_tien), 0)).where(
                SoQuy.tai_khoan == tk.ten_tk,
                SoQuy.loai == "chi",
                SoQuy.ngay >= sm,
                SoQuy.ngay < em,
            )
        ) or Decimal("0")
        thu_thang = Decimal(thu_thang)
        chi_thang = Decimal(chi_thang)
        so_du_cuoi = so_du_dau_thang + thu_thang - chi_thang

        items.append({
            "tai_khoan_id": tk.id,
            "ten_tk": tk.ten_tk,
            "loai": tk.loai,
            "so_du_dau_thang": str(so_du_dau_thang),
            "thu": str(thu_thang),
            "chi": str(chi_thang),
            "so_du_cuoi": str(so_du_cuoi),
        })
        tong_dau += so_du_dau_thang
        tong_thu += thu_thang
        tong_chi += chi_thang
        tong_cuoi += so_du_cuoi

    return {
        "thang": f"{sm.year}-{sm.month:02d}",
        "tu_ngay": sm.isoformat(),
        "den_ngay": em.isoformat(),  # exclusive — start of next month
        "items": items,
        "tong": {
            "so_du_dau_thang": str(tong_dau),
            "thu": str(tong_thu),
            "chi": str(tong_chi),
            "so_du_cuoi": str(tong_cuoi),
        },
    }


@router.get("/phan-loai-cf", response_model=list[PhanLoaiCfOut])
def list_phan_loai_cf(
    user: Annotated[JWTPayload, _AUTH],
    loai: Optional[str] = Query(None, pattern="^(thu|chi)$", description="thu | chi — bỏ trống = tất cả"),
):
    """Các mã "dòng tiền" (mã số báo cáo lưu chuyển tiền tệ) cho ô chọn ở hộp Lập phiếu thu/chi.

    Nguồn duy nhất: app/services/phan_loai_cf.py. Thứ tự theo mã số B03. PHẢI khai báo trước route động
    GET /{rid}, nếu không FastAPI hiểu "phan-loai-cf" là một rid.
    """
    return [PhanLoaiCfOut(**x._asdict(), nhom_ten=NHOM_TEN[x.nhom]) for x in ds_phan_loai_cf(loai)]


def _loi_nv(e: "nvsq.LoiNghiepVu") -> HTTPException:
    # detail là dict {ma, thong_bao, …}: máy đọc `ma`, giao diện hiện `thong_bao` (tiếng Việt) ngay dưới ô lỗi.
    return HTTPException(e.http, e.chi_tiet())


@router.get("/nghiep-vu", response_model=NghiepVuDsOut)
def list_nghiep_vu(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    loai: str = Query(..., pattern="^(thu|chi)$", description="thu | chi"),
):
    """Danh sách việc cho ô "Việc gì?" ở hộp Lập phiếu (đặc tả mục 4.3.1). Nguồn duy nhất:
    app/services/nghiep_vu_so_quy.py; số tài khoản theo `ketoan.cai_dat_he_thong.che_do`.
    Khai TRƯỚC route động GET /{rid}."""
    try:
        return nvsq.danh_sach(loai, nvsq.doc_che_do(db))
    except nvsq.LoiNghiepVu as e:
        raise _loi_nv(e)


@router.get("/theo-don/{ma_don}", response_model=TheoDonOut)
def so_quy_theo_don(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    ma_don: str = Path(..., min_length=3, max_length=64),
):
    """Tên khách + đã thu / đã hoàn / còn lại của một mã đơn — ô mã đơn ở hộp Lập phiếu tự điền."""
    return nvsq.theo_don(db, ma_don)


@router.get("", response_model=list[SoQuyOut])
def list_so_quy(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu_ngay: Optional[date_cls] = Query(None),
    den_ngay: Optional[date_cls] = Query(None),
    thang: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    loai: Optional[str] = Query(None, pattern="^(thu|chi)$"),
    tai_khoan: Optional[str] = None,
    ma_dinh_khoan: Optional[str] = Query(None, max_length=40, description="Lọc theo nghiệp vụ"),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = 0,
):
    stmt = select(SoQuy).order_by(SoQuy.ngay.desc(), SoQuy.id.desc())
    if ma_dinh_khoan:
        stmt = stmt.where(SoQuy.ma_dinh_khoan == ma_dinh_khoan)
    # Filter theo `thang=YYYY-MM` (FE đang gửi param này) — ưu tiên hơn tu/den_ngay.
    # Trước đây bị ignore → widget "Chi Tiết Giao Dịch" trả cả lịch sử all-time
    # thay vì chỉ tháng được chọn. Fix 27/05.
    if thang:
        sm, em = _parse_thang(thang)
        stmt = stmt.where(SoQuy.ngay >= sm).where(SoQuy.ngay < em)
    else:
        if tu_ngay:
            stmt = stmt.where(SoQuy.ngay >= tu_ngay)
        if den_ngay:
            stmt = stmt.where(SoQuy.ngay <= den_ngay)
    if loai:
        stmt = stmt.where(SoQuy.loai == loai)
    if tai_khoan:
        stmt = stmt.where(SoQuy.tai_khoan == tai_khoan)
    stmt = stmt.limit(limit).offset(offset)
    return db.execute(stmt).scalars().all()


@router.post("", response_model=SoQuyTaoOut, status_code=status.HTTP_201_CREATED)
def create_so_quy(
    body: SoQuyCreate,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    _require_admin(user)
    fields = body.model_dump(exclude_unset=True)
    if (fields.get("ma_dinh_khoan") or "").strip():
        return _tao_phieu_nghiep_vu(fields, request, response, db, user)
    # Không có nghiệp vụ → hành vi CŨ y nguyên (màn /app cũ gửi phan_loai_cf; cầu nối không đi qua đây).
    for k in ("ma_dinh_khoan", "ly_do", "xac_nhan_trung"):
        fields.pop(k, None)
    _kiem_dong_tien(fields.get("loai"), fields.get("phan_loai_cf"))
    # CHẶN chi làm số dư TK âm (anh Quang 2026-08-27)
    if (fields.get("loai") or "").lower() == "chi":
        from ..services.so_quy_auto import assert_du_chi
        assert_du_chi(db, fields.get("tai_khoan"), fields.get("so_tien"))
    # Issue 1 — auto-lookup nhan_vien_ten nếu chỉ truyền nhan_vien_id
    nv_id = fields.get("nhan_vien_id")
    if nv_id and not (fields.get("nhan_vien_ten") or "").strip():
        nv_ten = _lookup_nv_ten(db, nv_id)
        if nv_ten:
            fields["nhan_vien_ten"] = nv_ten
    obj = SoQuy(**fields, created_by=user.username)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="create_so_quy", user=user, request=request,
        resource=f"so_quy:{obj.id}",
        payload={"ngay": str(obj.ngay), "loai": obj.loai, "so_tien": str(obj.so_tien)},
    )
    return obj


def _tao_phieu_nghiep_vu(
    fields: dict[str, Any], request: Request, response: Response, db: Session, user: JWTPayload,
) -> SoQuyTaoOut:
    """Phiếu lập tay có ma_dinh_khoan (đặc tả 4.3.2): service kiểm + suy phan_loai_cf, router ghi + audit.
    Không gọi post_journal, không gọi is_ky_da_chot (giữ hành vi cũ — xử lý kỳ khoá ở bước sau)."""
    cu = nvsq.phieu_da_co(db, fields.get("ref_id"))
    if cu is not None:   # bấm Lưu hai lần cùng ref_id → trả lại dòng cũ, không ghi thêm
        response.status_code = status.HTTP_200_OK
        return SoQuyTaoOut.model_validate(cu)
    try:
        cot, dinh_khoan, canh_bao = nvsq.chuan_bi_phieu(db, fields, nvsq.doc_che_do(db))
    except nvsq.LoiNghiepVu as e:
        raise _loi_nv(e)
    if cot["loai"] == "chi":   # chặn chi làm âm số dư quỹ — giữ như phiếu cũ (anh Quang 2026-08-27)
        from ..services.so_quy_auto import assert_du_chi
        assert_du_chi(db, cot["tai_khoan"], cot["so_tien"])
    obj = SoQuy(**cot, created_by=user.username)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="create_so_quy", user=user, request=request,
        resource=f"so_quy:{obj.id}",
        payload={"ngay": str(obj.ngay), "loai": obj.loai, "so_tien": str(obj.so_tien),
                 "ma_dinh_khoan": obj.ma_dinh_khoan, "phan_loai_cf": obj.phan_loai_cf,
                 "doi_tuong_ma": obj.doi_tuong_ma, "ky": obj.ky},
    )
    return SoQuyTaoOut.model_validate(
        {**SoQuyOut.model_validate(obj).model_dump(), "dinh_khoan": dinh_khoan, "canh_bao": canh_bao}
    )


@router.get("/{rid}", response_model=SoQuyOut)
def get_so_quy(
    rid: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(SoQuy, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SoQuy không tồn tại")
    return obj


@router.put("/{rid}", response_model=SoQuyOut)
def update_so_quy(
    rid: int,
    body: SoQuyUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _CEO_EDIT],
):
    obj = db.get(SoQuy, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SoQuy không tồn tại")
    fields = body.model_dump(exclude_unset=True)
    # Dòng đã gắn nghiệp vụ: chưa có hook đảo bút toán nên KHÔNG cho đổi chiều / tiền / quỹ / nghiệp vụ / dòng tiền
    # (dòng tiền suy từ nghiệp vụ). Sửa ngày, nội dung, ghi chú vẫn được. Dòng cũ giữ nguyên hành vi.
    if obj.ma_dinh_khoan:
        doi = [k for k in ("loai", "so_tien", "tai_khoan", "ma_dinh_khoan", "phan_loai_cf")
               if k in fields and fields[k] != getattr(obj, k)]
        if doi:
            raise HTTPException(422, {
                "ma": "dong_da_gan_nghiep_vu", "truong": doi,
                "thong_bao": "Phiếu đã gắn nghiệp vụ — không đổi được loại phiếu, số tiền, quỹ, nghiệp vụ, dòng tiền. "
                             "Xoá phiếu rồi lập lại; sửa ngày / nội dung thì vẫn được.",
            })
    elif fields.get("ma_dinh_khoan"):
        raise HTTPException(422, {
            "ma": "chua_ho_tro_gan_nghiep_vu",
            "thong_bao": "Chưa gắn được nghiệp vụ cho phiếu có sẵn. Lập phiếu mới ở hộp Lập phiếu.",
        })
    fields.pop("ma_dinh_khoan", None)
    if fields.get("phan_loai_cf"):
        _kiem_dong_tien(fields.get("loai") or obj.loai, fields["phan_loai_cf"])
    # Issue 1 — re-lookup nhan_vien_ten khi đổi nhan_vien_id mà không truyền tên
    if "nhan_vien_id" in fields and not (fields.get("nhan_vien_ten") or "").strip():
        nv_ten = _lookup_nv_ten(db, fields["nhan_vien_id"])
        if nv_ten:
            fields["nhan_vien_ten"] = nv_ten
    for k, v in fields.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="update_so_quy", user=user, request=request,
        resource=f"so_quy:{rid}", payload=fields,
    )
    return obj


@router.delete("/{rid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_so_quy(
    rid: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _CEO_EDIT],
):
    obj = db.get(SoQuy, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SoQuy không tồn tại")
    db.delete(obj)
    db.commit()
    log_action(
        db, app="ketoan", action="delete_so_quy", user=user, request=request,
        resource=f"so_quy:{rid}",
    )


# ───────────────────── Chuyển nội bộ giữa 2 TK ─────────────────────────

class ChuyenNoiBoIn(BaseModel):
    ngay: date_cls
    tu_tai_khoan: str       # tên TK rút (Chi)
    den_tai_khoan: str      # tên TK nạp (Thu)
    so_tien: float
    noi_dung: Optional[str] = ""
    ghi_chu: Optional[str] = ""
    ref_id: Optional[str] = None  # cho idempotent — client gen UUID


@router.post("/chuyen-noi-bo", status_code=status.HTTP_201_CREATED)
def chuyen_noi_bo(
    body: ChuyenNoiBoIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
) -> dict[str, Any]:
    """Chuyển tiền giữa 2 tài khoản — tạo 2 entry idempotent.

    - Chi từ `tu_tai_khoan` (loai='chi')
    - Thu vào `den_tai_khoan` (loai='thu')
    - Cùng `ref_id` để link 2 entry. Re-call cùng ref_id → no-op (trả entry cũ).
    """
    if body.tu_tai_khoan == body.den_tai_khoan:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "TK nguồn và TK đích phải khác nhau",
        )
    if body.so_tien <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Số tiền phải > 0")

    # CHẶN chuyển đi làm số dư TK nguồn âm (anh Quang 2026-08-27)
    from ..services.so_quy_auto import assert_du_chi
    assert_du_chi(db, body.tu_tai_khoan, body.so_tien)

    ref_id = (body.ref_id or f"chuyennb_{uuid4().hex[:12]}")
    so_tien = Decimal(str(body.so_tien))

    # Idempotent: nếu đã có 2 entry cùng ref_id → trả luôn
    existing = db.execute(
        select(SoQuy).where(SoQuy.ref_id == ref_id)
    ).scalars().all()
    if existing:
        return {
            "ok": True,
            "ref_id": ref_id,
            "entries": [{"id": e.id, "loai": e.loai, "tk": e.tai_khoan, "so_tien": float(e.so_tien)} for e in existing],
            "idempotent_hit": True,
        }

    noi_dung_chi = (body.noi_dung or "").strip() or f"Chuyển sang {body.den_tai_khoan}"
    noi_dung_thu = (body.noi_dung or "").strip() or f"Nhận từ {body.tu_tai_khoan}"
    # 01/10/2026: cặp mới ghi nghiệp vụ 'chuyen_noi_bo' + dòng tiền 'noi_bo' (trước: 'khac'). Báo cáo lưu chuyển
    # tiền tệ loại chuyển nội bộ theo lien_quan='chuyen_noi_bo' HOẶC phan_loai_cf='noi_bo' (bao_cao_cashflow.py
    # _khong_noi_bo / _full_chi_classified_ids) nên số báo cáo không đổi. Dòng cũ giữ 'khac', không sửa.

    sq_chi = SoQuy(
        ngay=body.ngay,
        loai="chi",
        so_tien=so_tien,
        tai_khoan=body.tu_tai_khoan,
        noi_dung=noi_dung_chi,
        lien_quan="chuyen_noi_bo",
        phan_loai_cf="noi_bo",
        ma_dinh_khoan="chuyen_noi_bo",
        ref_id=ref_id,
        ghi_chu=body.ghi_chu or None,
        created_by=user.username,
    )
    sq_thu = SoQuy(
        ngay=body.ngay,
        loai="thu",
        so_tien=so_tien,
        tai_khoan=body.den_tai_khoan,
        noi_dung=noi_dung_thu,
        lien_quan="chuyen_noi_bo",
        phan_loai_cf="noi_bo",
        ma_dinh_khoan="chuyen_noi_bo",
        ref_id=ref_id,
        ghi_chu=body.ghi_chu or None,
        created_by=user.username,
    )
    db.add(sq_chi)
    db.add(sq_thu)
    db.commit()
    db.refresh(sq_chi)
    db.refresh(sq_thu)

    log_action(
        db, app="ketoan", action="so_quy_chuyen_noi_bo",
        user=user, request=request, resource=f"so_quy:{ref_id}",
        payload={
            "tu": body.tu_tai_khoan, "den": body.den_tai_khoan,
            "so_tien": float(so_tien),
        },
    )
    return {
        "ok": True,
        "ref_id": ref_id,
        "entries": [
            {"id": sq_chi.id, "loai": "chi", "tk": sq_chi.tai_khoan, "so_tien": float(sq_chi.so_tien)},
            {"id": sq_thu.id, "loai": "thu", "tk": sq_thu.tai_khoan, "so_tien": float(sq_thu.so_tien)},
        ],
        "idempotent_hit": False,
    }
