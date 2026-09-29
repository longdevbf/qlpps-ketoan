"""CongNo API — CRUD + POST /{id}/tra (cập nhật trạng thái trả nợ)."""
from datetime import date as date_cls
from decimal import Decimal
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import CongNo, SoQuy
from ..schemas import CongNoCreate, CongNoUpdate, CongNoOut, CongNoTraBody
from ..services import next_cong_no_id
from ..services.cong_no_dong_bo import (
    NGUON_BAO_GIA, NGUON_HOP_LE, NGUON_MUA_HANG, dong_bo_cong_no,
)
from ..services.cong_no_tra_nhieu import tra_nhieu
from ..services.tim_kiem import khop_mot_trong
from ._deps import require_ketoan_user, require_ceo_thuchi


router = APIRouter()
_AUTH = Depends(require_ketoan_user)
_CEO_EDIT = Depends(require_ceo_thuchi)  # sửa/xoá công nợ → chỉ CEO (đồng bộ thu-chi)


@router.get("", response_model=list[CongNoOut])
def list_cong_no(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    loai: Optional[str] = Query(None, pattern="^(phai_thu|phai_tra)$"),
    trang_thai: Optional[str] = Query(None, pattern="^(chua_tra|da_tra)$"),
    tu_ngay: Optional[date_cls] = None,
    den_ngay: Optional[date_cls] = None,
    doi_tac: Optional[str] = None,
    q: Optional[str] = None,   # search theo mã đơn hoặc đối tác/KH/NCC
    limit: int = Query(500, ge=1, le=2000),
    offset: int = 0,
):
    stmt = select(CongNo).order_by(CongNo.ngay.desc(), CongNo.id.desc())
    if loai:
        stmt = stmt.where(CongNo.loai == loai)
    if trang_thai:
        stmt = stmt.where(CongNo.trang_thai == trang_thai)
    if tu_ngay:
        stmt = stmt.where(CongNo.ngay >= tu_ngay)
    if den_ngay:
        stmt = stmt.where(CongNo.ngay <= den_ngay)
    if doi_tac:
        # Khớp CHÍNH XÁC (không ilike substring) — `doi_tac` là khoá "mã khách"
        # tạm của app Kế toán (không có id khách hàng riêng), dùng bởi
        # kt-doi-tuong.js để tổng hợp công nợ CHỈ của MỘT đối tác. ilike
        # substring trước đây khiến vd doi_tac='Anh Nam' gộp nhầm cả dòng
        # 'anh Nam' (khác hoa/thường) của KHÁCH KHÁC vào tổng — sai số liệu
        # hiển thị ở /ketoan/doi-tuong. Tìm kiếm mờ (gõ một phần tên) vẫn
        # dùng `q` (see filter phía dưới), không đụng tới đây.
        stmt = stmt.where(CongNo.doi_tac == doi_tac)
    if q and q.strip():
        # Không phân biệt dấu + hoa/thường ("chien" ra "CHIẾN PHƯƠNG") — services/tim_kiem.py.
        stmt = stmt.where(khop_mot_trong((CongNo.doi_tac, CongNo.ma_don), q))
    stmt = stmt.limit(limit).offset(offset)
    return db.execute(stmt).scalars().all()


@router.post("", response_model=CongNoOut, status_code=status.HTTP_201_CREATED)
def create_cong_no(
    body: CongNoCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    cid = body.id or next_cong_no_id(db)
    if db.get(CongNo, cid):
        raise HTTPException(status.HTTP_409_CONFLICT, f"CongNo id {cid} đã tồn tại")
    data = body.model_dump(exclude_unset=True, exclude={"id"})
    # tai_khoan KHÔNG phải column CongNo — chỉ để forward cho SoQuy sync
    tai_khoan_for_sq = data.pop("tai_khoan", None)
    # Auto-trang_thai: da_tra >= so_tien (và so_tien > 0) → 'da_tra'.
    # Case đặt cọc dư: da_tra > so_tien → cũng đánh dấu 'da_tra' + ngay_tra.
    # FE không cần set trang_thai; backend tự suy luận.
    so_tien = Decimal(data.get("so_tien", 0) or 0)
    da_tra = Decimal(data.get("da_tra", 0) or 0)
    if so_tien > 0 and da_tra >= so_tien:
        data["trang_thai"] = "da_tra"
        if not data.get("ngay_tra"):
            data["ngay_tra"] = date_cls.today()
    obj = CongNo(id=cid, created_by=user.username, **data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    # Sync sổ quỹ khi tạo CN với da_tra > 0 (vd đặt cọc đã trả). Auto-bridge
    # tạo SoQuy chi/thu khớp khoản đã trả ban đầu.
    if da_tra > 0:
        try:
            from ..services.so_quy_auto import sync_so_quy_from_cong_no_payment
            sync_so_quy_from_cong_no_payment(
                db, obj, da_tra, tai_khoan=tai_khoan_for_sq,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "create_cong_no: so_quy sync failed for %s: %s", cid, e,
            )
    log_action(
        db, app="ketoan", action="create_cong_no", user=user, request=request,
        resource=f"cong_no:{cid}",
        payload={"loai": obj.loai, "doi_tac": obj.doi_tac, "so_tien": str(obj.so_tien)},
    )
    return obj


# Nút "⬇ MH / ⬇ KD / ⬇ Import Tất Cả" của màn cũ /app#cong-no gửi source=mua_hang|sale_admin|all
# (bản trước chỉ nhận baogia|muahang → 422; nhánh baogia còn tạo dòng ref_source='baogia' TRÙNG dòng
# 'baogia_quote' của /sync). Nay /import = /sync (một đường ghi duy nhất, services/cong_no_dong_bo.py).
_IMPORT_NGUON = {
    "all": NGUON_HOP_LE, "baogia": (NGUON_BAO_GIA,), "sale_admin": (NGUON_BAO_GIA,),
    "muahang": (NGUON_MUA_HANG,), "mua_hang": (NGUON_MUA_HANG,),
}


class CongNoImportBody(BaseModel):
    source: str = Field(..., pattern="^(" + "|".join(_IMPORT_NGUON) + ")$")


def _chay_dong_bo(db: Session, user: JWTPayload, request: Request, nguon: list[str] | tuple[str, ...], dry_run: bool,
                  action: str) -> dict[str, Any]:
    kq = dong_bo_cong_no(db, nguon=nguon, user=user, dry_run=dry_run)
    if not dry_run:
        log_action(
            db, app="ketoan", action=action, user=user, request=request, resource="cong_no:sync",
            payload={"nguon": kq["nguon"], "summary": kq["summary"], "detail": kq["detail"],
                     "ids": [d["id"] for d in kq["dong"]]},
        )
    return kq


@router.post("/import")
def import_cong_no(
    body: CongNoImportBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
) -> dict[str, Any]:
    """Tương thích màn cũ: chạy đồng bộ thật cho nguồn đã chọn. Trả thêm `added`/`total` màn cũ đọc."""
    kq = _chay_dong_bo(db, user, request, _IMPORT_NGUON[body.source], False, "import_cong_no")
    s = kq["summary"]
    return {**kq, "source": body.source, "added": s["tao_moi"], "imported": s["tao_moi"],
            "skipped": s["bo_qua"], "total": db.query(CongNo).count()}


@router.get("/{cid}", response_model=CongNoOut)
def get_cong_no(
    cid: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(CongNo, cid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CongNo không tồn tại")
    return obj


@router.put("/{cid}", response_model=CongNoOut)
def update_cong_no(
    cid: str,
    body: CongNoUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _CEO_EDIT],
):
    obj = db.get(CongNo, cid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CongNo không tồn tại")
    fields = body.model_dump(exclude_unset=True)
    # tai_khoan KHÔNG phải column CongNo — pop riêng cho SoQuy sync
    tai_khoan_for_sq = fields.pop("tai_khoan", None)
    old_da_tra = Decimal(obj.da_tra or 0)
    for k, v in fields.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    # Sync sổ quỹ nếu da_tra TĂNG qua PUT (vd kế toán sửa trực tiếp khoản trả).
    # Nếu giảm → bỏ qua (không reversed sổ quỹ tự động — cần manual cleanup).
    new_da_tra = Decimal(obj.da_tra or 0)
    paid_delta = new_da_tra - old_da_tra
    if paid_delta > 0:
        if obj.loai == "phai_tra" and tai_khoan_for_sq:
            from ..services.so_quy_auto import assert_du_chi as _assert_du_chi
            _assert_du_chi(db, tai_khoan_for_sq, paid_delta)  # chặn trả nợ làm âm
        try:
            from ..services.so_quy_auto import sync_so_quy_from_cong_no_payment
            sync_so_quy_from_cong_no_payment(
                db, obj, paid_delta, tai_khoan=tai_khoan_for_sq,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "update_cong_no: so_quy sync failed for %s: %s", cid, e,
            )
    log_action(
        db, app="ketoan", action="update_cong_no", user=user, request=request,
        # jsonable_encoder: fields có Decimal/date — trước đây json.dumps lỗi nên audit sửa công nợ bị bỏ âm thầm.
        resource=f"cong_no:{cid}", payload=jsonable_encoder(fields),
    )
    return obj


class TraNhieuDong(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    so_tien: Decimal = Field(..., gt=0, decimal_places=2)


class TraNhieuBody(BaseModel):
    tai_khoan: str = Field(..., min_length=1, max_length=120)
    ngay_tra: Optional[date_cls] = None
    ghi_chu: Optional[str] = Field(None, max_length=500)
    dong: list[TraNhieuDong] = Field(..., min_length=1, max_length=500)


@router.post("/tra-nhieu")
def tra_nhieu_cong_no(
    body: TraNhieuBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    dry_run: bool = False,
):
    """Ghi nhận thu/trả NHIỀU khoản trong MỘT giao dịch (all-or-nothing), cùng cơ chế `/{id}/tra`.

    `dry_run=true`: validate + tính đủ (da_tra/con_lai mới, dòng sổ quỹ sẽ tạo, tổng) rồi rollback.
    Logic ở services/cong_no_tra_nhieu.py.
    """
    return tra_nhieu(
        db, dong=[(d.id, d.so_tien) for d in body.dong], tai_khoan=body.tai_khoan.strip(),
        ngay_tra=body.ngay_tra, ghi_chu=(body.ghi_chu or "").strip() or None,
        user=user, request=request, dry_run=dry_run,
    )


@router.post("/{cid}/tra", response_model=CongNoOut)
def tra_cong_no(
    cid: str,
    body: CongNoTraBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Đánh dấu trả công nợ. Nếu `da_tra >= so_tien` → trang_thai = 'da_tra'."""
    obj = db.get(CongNo, cid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CongNo không tồn tại")

    old_da_tra = Decimal(obj.da_tra or 0)
    da_tra = body.da_tra if body.da_tra is not None else obj.so_tien
    obj.da_tra = Decimal(da_tra)
    paid_delta = Decimal(obj.da_tra) - old_da_tra
    if Decimal(obj.da_tra) >= Decimal(obj.so_tien):
        obj.trang_thai = "da_tra"
        obj.ngay_tra = body.ngay_tra or date_cls.today()
    else:
        obj.trang_thai = "chua_tra"
    if body.ghi_chu:
        obj.ghi_chu = body.ghi_chu

    # Chặn trả nợ làm âm quỹ TRƯỚC khi commit — trước 25/09/2026 kiểm sau commit nên
    # thiếu tiền thì API báo 400, không ghi sổ quỹ, nhưng công nợ đã bị trừ.
    if paid_delta > 0 and obj.loai == "phai_tra" and body.tai_khoan:
        from ..services.so_quy_auto import assert_du_chi as _assert_du_chi
        try:
            _assert_du_chi(db, body.tai_khoan, paid_delta)
        except Exception:
            db.rollback()
            raise

    db.commit()
    db.refresh(obj)
    # Auto-create SoQuy chi/thu cho khoản trả delta — tách theo tài khoản
    if paid_delta and paid_delta > 0:
        try:
            from ..services.so_quy_auto import sync_so_quy_from_cong_no_payment
            sync_so_quy_from_cong_no_payment(
                db, obj, paid_delta,
                tai_khoan=body.tai_khoan,
                ngay_thanh_toan=body.ngay_tra or date_cls.today(),
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "tra_cong_no: so_quy sync failed for %s: %s", cid, e,
            )
    log_action(
        db, app="ketoan", action="tra_cong_no", user=user, request=request,
        resource=f"cong_no:{cid}",
        payload={"da_tra": str(obj.da_tra), "trang_thai": obj.trang_thai},
    )
    return obj


@router.delete("/{cid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cong_no(
    cid: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _CEO_EDIT],
):
    obj = db.get(CongNo, cid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CongNo không tồn tại")
    # Xóa cascade sổ quỹ liên quan — KHỚP CHÍNH XÁC theo ref_id, KHÔNG dùng
    # '%cid%' (substring): ref_id='{cid}-DA{seq}' → '%CN-2026-001%' sẽ khớp NHẦM
    # 'CN-2026-0010', '...0011'... của công nợ khác → xoá mất sổ quỹ đơn khác.
    # (anh Quang 2026-08-28, DB-01)
    from sqlalchemy import delete as sql_delete, or_ as _or
    db.execute(
        sql_delete(SoQuy).where(
            SoQuy.lien_quan == "cong_no",
            _or(SoQuy.ref_id == cid, SoQuy.ref_id.like(f"{cid}-DA%")),
        )
    )
    db.delete(obj)
    db.commit()
    log_action(
        db, app="ketoan", action="delete_cong_no", user=user, request=request,
        resource=f"cong_no:{cid}",
    )


# ════════════════════════════════════════════════════════════════════════════
# SYNC từ các app khác — pull số liệu công nợ tự động
# ════════════════════════════════════════════════════════════════════════════

@router.post("/sync")
def sync_cong_no_from_apps(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    sources: Optional[list[str]] = Query(
        default=None, description="'baogia' (phải thu KH), 'muahang' (phải trả NCC). Mặc định: cả hai.",
    ),
    dry_run: bool = False,
) -> dict[str, Any]:
    """Đồng bộ công nợ: Báo giá đã duyệt → phải thu KH (tạo + CẬP NHẬT theo "Còn thu" màn Đơn hàng),
    PO Mua hàng đã có hàng chưa có công nợ → phải trả NCC. Chi tiết: services/cong_no_dong_bo.py.

    `dry_run=true`: chạy y hệt rồi rollback — trả số dòng tạo/cập nhật/bỏ qua, tổng trước/sau theo
    KH/NCC, từng dòng thay đổi. Chạy lại lần 2 không thay đổi gì (idempotent)."""
    nguon = sources or list(NGUON_HOP_LE)
    sai = [n for n in nguon if n not in NGUON_HOP_LE]
    if sai:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Nguồn không hỗ trợ: {', '.join(sai)}. Chỉ nhận: {', '.join(NGUON_HOP_LE)} "
            "(Sale Admin không còn đồng bộ — thu hộ trùng phải thu đơn, cước ĐVVC trả qua Đề nghị TT).",
        )
    return _chay_dong_bo(db, user, request, nguon, dry_run, "sync_cong_no")
