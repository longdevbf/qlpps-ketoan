"""DoanhThu API — CRUD."""
from datetime import date as date_cls
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func as sqlfunc, select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db
from shared.events import emit_event

from ..models import DoanhThu
from ..schemas import DoanhThuCreate, DoanhThuUpdate, DoanhThuOut
from ._deps import require_ketoan_user, require_ceo_thuchi


router = APIRouter()
_AUTH = Depends(require_ketoan_user)
_CEO_EDIT = Depends(require_ceo_thuchi)  # sửa/xoá doanh thu → chỉ CEO


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

        cn.da_tra = total
        so_tien = Decimal(str(cn.so_tien or 0))
        if so_tien > 0 and total >= so_tien:
            cn.trang_thai = "da_tra"
            if not cn.ngay_tra:
                cn.ngay_tra = date_cls.today()
        else:
            cn.trang_thai = "chua_tra"
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
    limit: int = 500,
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
    log_action(
        db, app="ketoan", action="create_doanh_thu", user=user, request=request,
        resource=f"doanh_thu:{obj.id}",
        payload={"ngay": str(obj.ngay), "so_tien": str(obj.so_tien)},
    )
    emit_event("revenue:new", {
        "id": obj.id, "ngay": str(obj.ngay) if obj.ngay else None,
        "so_tien": float(obj.so_tien or 0), "loai": getattr(obj, "loai", None),
    })
    return obj


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
    log_action(
        db, app="ketoan", action="delete_doanh_thu", user=user, request=request,
        resource=f"doanh_thu:{rid}",
    )
