"""DoanhThu API — CRUD."""
from datetime import date as date_cls
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func as sqlfunc, select, text
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db
from shared.events import emit_event

from ..models import DoanhThu
from ..schemas import DoanhThuCreate, DoanhThuUpdate, DoanhThuOut
from ..schemas.doanh_thu import DoanhThuChiTietOut, KhachTheoDonOut
from ..services.thu_chi_chi_tiet import doc_khach_theo_don
from ._deps import require_ketoan_user, require_ceo_thuchi


router = APIRouter()
_AUTH = Depends(require_ketoan_user)
_CEO_EDIT = Depends(require_ceo_thuchi)  # sửa/xoá doanh thu → chỉ CEO


def _bust_pl_cache() -> None:
    """Xoá cache P&L khi doanh thu đổi → báo cáo không bị số cũ (PERF-05)."""
    try:
        from .bao_cao_pnl import invalidate_pl_cache
        invalidate_pl_cache()
    except Exception:
        pass


def _nguon_doanh_thu(o) -> Optional[str]:
    """Phân loại 1 dòng doanh thu: TỰ ĐỘNG theo luồng vs KT tự nhập tay.

    Trả nhãn luồng (badge '🔄 ...') nếu do hệ thống sinh từ luồng; None nếu KT
    nhập tay (badge '✍️ Tự nhập').
      - ref_order_id  → auto từ PO mua hàng (revenue_from_order).
      - ma_don + 'cọc'       → luồng Duyệt cọc (kt_duyet / cọc bổ sung).
      - ma_don + 'thanh toán'→ luồng Đối chiếu giao hàng (external hoàn thành).
      - ma_don khác / nguon='kd' → Theo đơn.
    """
    ltt = (o.loai_thanh_toan or "").lower()
    if o.ref_order_id:
        return "PO mua hàng"
    if o.ma_don:
        if "cọc" in ltt or "coc" in ltt:
            return "Duyệt cọc"
        if "thanh toán" in ltt or "thanh toan" in ltt:
            return "Đối chiếu giao hàng"
        return "Theo đơn"
    if (o.nguon or "").lower() == "kd":
        return "Theo đơn"
    return None


def _sync_cong_no_da_thu(db: Session, ma_don: Optional[str]) -> None:
    """Sau khi create/update/delete doanh_thu, đồng bộ cong_no.da_tra cho mã đơn đó.

    Logic: da_tra = Σ doanh_thu.so_tien theo ma_don (tất cả loại, bao gồm Hoàn Tiền
    với giá trị âm nếu kế toán nhập âm; hoặc dương cho Đặt Cọc/Thanh Toán).
    Cập nhật trang_thai tự động: da_tra >= so_tien → 'da_tra'.
    """
    if not ma_don:
        return
    try:
        from ..models import CongNo
        total = db.execute(
            select(sqlfunc.coalesce(sqlfunc.sum(DoanhThu.so_tien), 0))
            .where(DoanhThu.ma_don == ma_don)
        ).scalar() or Decimal("0")
        total = Decimal(str(total))

        cn = db.execute(
            select(CongNo)
            .where(CongNo.ma_don == ma_don)
            .where(CongNo.loai == "phai_thu")
        ).scalar_one_or_none()
        if not cn:
            return

        # LOG-08 (2026-08-28): KHÔNG clobber da_tra xuống dưới mức đã ghi qua kênh
        # khác (tra_cong_no / thu hộ ĐVVC) — dùng MAX. Và KHÔNG tự lật 'da_tra'→
        # 'chua_tra' (chỉ NÂNG lên da_tra khi đủ tiền), tránh đảo ngược đơn đã tất toán.
        cn.da_tra = max(Decimal(str(cn.da_tra or 0)), total)
        so_tien = Decimal(str(cn.so_tien or 0))
        if so_tien > 0 and Decimal(str(cn.da_tra or 0)) >= so_tien:
            cn.trang_thai = "da_tra"
            if not cn.ngay_tra:
                cn.ngay_tra = date_cls.today()
        db.commit()
    except Exception:
        db.rollback()


@router.get("", response_model=list[DoanhThuOut])
def list_doanh_thu(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu_ngay: Optional[date_cls] = Query(None),
    den_ngay: Optional[date_cls] = Query(None),
    loai: Optional[str] = None,
    nv_kinh_doanh: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
    offset: int = 0,
):
    stmt = select(DoanhThu).order_by(DoanhThu.ngay.desc(), DoanhThu.id.desc())
    if tu_ngay:
        stmt = stmt.where(DoanhThu.ngay >= tu_ngay)
    if den_ngay:
        stmt = stmt.where(DoanhThu.ngay <= den_ngay)
    if loai:
        stmt = stmt.where(DoanhThu.loai == loai)
    if nv_kinh_doanh:
        stmt = stmt.where(DoanhThu.nv_kinh_doanh == nv_kinh_doanh)
    stmt = stmt.limit(limit).offset(offset)
    rows = db.execute(stmt).scalars().all()
    for o in rows:
        o.nguon_hien = _nguon_doanh_thu(o)  # phân loại luồng vs tự nhập
    return rows


@router.post("", response_model=DoanhThuOut, status_code=status.HTTP_201_CREATED)
def create_doanh_thu(
    body: DoanhThuCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = DoanhThu(**body.model_dump(exclude_unset=True), created_by=user.username)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    # Auto-create SoQuy thu — fail-soft
    try:
        from ..services.so_quy_auto import sync_so_quy_from_doanh_thu
        sync_so_quy_from_doanh_thu(db, obj)
    except Exception:
        pass
    # Cập nhật da_tra trong cong_no tương ứng
    _sync_cong_no_da_thu(db, obj.ma_don)
    _bust_pl_cache()
    log_action(
        db, app="ketoan", action="create_doanh_thu", user=user, request=request,
        resource=f"doanh_thu:{obj.id}",
        payload={"ngay": str(obj.ngay), "so_tien": str(obj.so_tien), "nguoi_nop": obj.nguoi_nop},
    )
    emit_event("revenue:new", {
        "id": obj.id, "ngay": str(obj.ngay) if obj.ngay else None,
        "so_tien": float(obj.so_tien or 0), "loai": getattr(obj, "loai", None),
    })
    return obj


@router.get("/by-month")
def doanh_thu_by_month(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Tổng hợp doanh thu THEO THÁNG ở server (GROUP BY) — thay việc FE kéo TOÀN BỘ
    bảng (?limit=100000) rồi gộp client (PERF-01, 2026-08-28). Trả ~vài chục dòng."""
    rows = db.execute(text("""
        SELECT to_char(ngay, 'YYYY-MM') AS thang,
               COALESCE(SUM(so_tien), 0) AS tong,
               COALESCE(SUM(CASE WHEN loai_thanh_toan ILIKE '%cọc%'      THEN so_tien ELSE 0 END), 0) AS coc,
               COALESCE(SUM(CASE WHEN loai_thanh_toan ILIKE 'thanh toán' THEN so_tien ELSE 0 END), 0) AS tt,
               COUNT(*) AS count
        FROM ketoan.doanh_thu
        GROUP BY 1 ORDER BY 1
    """)).mappings().all()
    return [{"thang": r["thang"], "tong": float(r["tong"] or 0), "coc": float(r["coc"] or 0),
             "tt": float(r["tt"] or 0), "count": int(r["count"] or 0)} for r in rows]


# "/khach-theo-don" PHẢI khai trước "/{rid}": FastAPI so đường dẫn theo thứ tự khai báo, đứng sau thì
# "/{rid}" bắt trước rồi trả 422 vì "khach-theo-don" không phải số nguyên.
@router.get("/khach-theo-don", response_model=KhachTheoDonOut)
def khach_theo_don(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    ma_don: str = Query(..., min_length=1, max_length=64),
):
    """Khách của một mã đơn (baogia.quotes) — hộp "Ghi nhận doanh thu" điền sẵn ô Người nộp."""
    khach, doc_duoc = doc_khach_theo_don(db, ma_don)
    return {"ma_don": ma_don.strip(), "doc_duoc": doc_duoc, "khach": khach}


@router.get("/{rid}/chi-tiet", response_model=DoanhThuChiTietOut)
def chi_tiet_doanh_thu(
    rid: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Popup chi tiết một phiếu doanh thu (màn Thu chi): mọi cột + khách của đơn, một lần gọi."""
    obj = db.get(DoanhThu, rid)
    if not obj:
        # Câu này hiện thẳng trong khối lỗi của popup → nói bằng chữ người đọc, không dùng tên class.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Không tìm thấy phiếu doanh thu DT-{rid} — có thể vừa bị xoá. "
            "Đóng cửa sổ này rồi tải lại trang để cập nhật danh sách.",
        )
    obj.nguon_hien = _nguon_doanh_thu(obj)
    # Chụp dữ liệu phiếu ra dict TRƯỚC khi đọc chéo app: đọc lỗi thì savepoint bị huỷ,
    # không kéo theo đối tượng ORM.
    du_lieu = DoanhThuChiTietOut.model_validate(obj).model_dump()
    du_lieu["khach"], du_lieu["khach_doc_duoc"] = doc_khach_theo_don(db, du_lieu["ma_don"])
    return du_lieu


@router.get("/{rid}", response_model=DoanhThuOut)
def get_doanh_thu(
    rid: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(DoanhThu, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "DoanhThu không tồn tại")
    return obj


@router.put("/{rid}", response_model=DoanhThuOut)
def update_doanh_thu(
    rid: int,
    body: DoanhThuUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _CEO_EDIT],
):
    obj = db.get(DoanhThu, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "DoanhThu không tồn tại")
    old_ma_don = obj.ma_don  # giữ trước khi overwrite
    fields = body.model_dump(exclude_unset=True)
    for k, v in fields.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    # Sync SoQuy nếu so_tien hoặc ngày thay đổi
    try:
        from ..services.so_quy_auto import sync_so_quy_from_doanh_thu
        sync_so_quy_from_doanh_thu(db, obj)
    except Exception:
        pass
    # Cập nhật da_tra cho cả ma_don mới lẫn ma_don cũ (nếu bị đổi)
    _sync_cong_no_da_thu(db, obj.ma_don)
    if old_ma_don and old_ma_don != obj.ma_don:
        _sync_cong_no_da_thu(db, old_ma_don)
    _bust_pl_cache()
    log_action(
        db, app="ketoan", action="update_doanh_thu", user=user, request=request,
        resource=f"doanh_thu:{rid}", payload=fields,
    )
    return obj


@router.delete("/{rid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doanh_thu(
    rid: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _CEO_EDIT],
):
    obj = db.get(DoanhThu, rid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "DoanhThu không tồn tại")
    ma_don_deleted = obj.ma_don  # giữ trước khi xóa
    db.delete(obj)
    db.commit()
    # Xoá SoQuy thu liên quan — fail-soft
    try:
        from ..models import SoQuy
        from sqlalchemy import delete as sql_delete
        db.execute(
            sql_delete(SoQuy).where(SoQuy.lien_quan == "doanh_thu", SoQuy.ref_id == f"DT-{rid}")
        )
        db.commit()
    except Exception:
        db.rollback()
    # Recalc da_tra sau khi xóa
    _sync_cong_no_da_thu(db, ma_don_deleted)
    _bust_pl_cache()
    log_action(
        db, app="ketoan", action="delete_doanh_thu", user=user, request=request,
        resource=f"doanh_thu:{rid}",
    )
