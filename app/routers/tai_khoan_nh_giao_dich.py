"""TaiKhoanNHGiaoDich API — nhật ký thu/chi của tài khoản ngân hàng.

Endpoints:
    GET    /api/tai-khoan/{tk_id}/giao-dich      (list + computed so_du running)
    GET    /api/tai-khoan/{tk_id}/so-du          (= SUM(thu) - SUM(chi))
    POST   /api/tai-khoan/{tk_id}/giao-dich      (manual ghi nhận thu/chi)
    DELETE /api/tai-khoan/giao-dich/{gd_id}      (admin only)

Audit dữ liệu 2026-09-25 (màn "Ngân hàng"): 2 endpoint GET trước đây đọc bảng
`ketoan.tai_khoan_nh_giao_dich`, nhưng bảng này CHỈ được vài luồng lẻ (khoản vay,
TSCĐ...) ghi tay khi có `tai_khoan_id` — không phải sổ giao dịch đầy đủ của tài
khoản: đối chiếu với DB thấy nó THIẾU toàn bộ phần thu từ Doanh Thu (tài khoản
ACB/BIDV có hàng trăm giao dịch thật trong `ketoan.so_quy` nhưng 0 dòng ở đây),
và có cả bản ghi trùng lặp (vd 2 dòng "Giải ngân vay" giống hệt nhau cho VPB).
→ 2 endpoint GET bên dưới đổi sang đọc `ketoan.so_quy` (lọc theo
`tai_khoan = TaiKhoanNH.ten_tk`) — đúng là sổ quỹ tổng hợp auto-sync từ Doanh
Thu/Chi Phí/Công Nợ/chuyển nội bộ/vay (xem `services/so_quy_auto.py`), đã được
màn Sổ Quỹ dùng và đối chiếu khớp DB. Endpoint POST/DELETE bên dưới GIỮ NGUYÊN
(ghi vào tai_khoan_nh_giao_dich, do các router khác — chi_phi/khoan_vay/tscd...
— còn phụ thuộc), chỉ không còn được 2 endpoint GET đọc lại nữa.
"""
from datetime import date as date_cls
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import SoQuy, TaiKhoanNH, TaiKhoanNHGiaoDich
from ..schemas import (
    TaiKhoanNHGiaoDichCreate, TaiKhoanNHGiaoDichOut, TaiKhoanSoDuOut,
)
from ..services.journal import danh_muc_tk, post_journal
from ..services.tai_khoan_tien import tk_tien_cua
from ..services.so_quy_auto import so_du_hien_tai, so_du_truoc_ngay
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


def _ensure_tai_khoan(db: Session, tk_id: int) -> TaiKhoanNH:
    tk = db.get(TaiKhoanNH, tk_id)
    if not tk:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "TaiKhoanNH không tồn tại")
    return tk


@router.get("/{tk_id}/giao-dich", response_model=list[TaiKhoanNHGiaoDichOut])
def list_giao_dich(
    tk_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    from_date: Optional[date_cls] = Query(None, alias="from"),
    to_date: Optional[date_cls] = Query(None, alias="to"),
    limit: int = 1000,
    offset: int = 0,
):
    """List giao dịch của TK (nguồn: `ketoan.so_quy`, xem docstring đầu file) +
    computed so_du_sau (running balance theo ngày + id).

    `so_du_sau` cộng dồn từ tồn đầu kỳ THẬT tại `from_date` (qua
    `so_quy_auto.so_du_truoc_ngay`, cùng thuật toán neo với màn Sổ Quỹ) — trước
    đây luôn cộng dồn từ 0 bất kể `from_date`, nên lọc theo tháng/kỳ bất kỳ đều
    ra "Số dư sau" sai (không khớp KPI "Số dư trên sổ" lấy từ /so-du).
    """
    tk = _ensure_tai_khoan(db, tk_id)

    stmt = (
        select(SoQuy)
        .where(SoQuy.tai_khoan == tk.ten_tk)
        .order_by(SoQuy.ngay.asc(), SoQuy.id.asc())
    )
    if from_date:
        stmt = stmt.where(SoQuy.ngay >= from_date)
    if to_date:
        stmt = stmt.where(SoQuy.ngay <= to_date)
    stmt = stmt.limit(limit).offset(offset)

    items = db.execute(stmt).scalars().all()
    so_du = so_du_truoc_ngay(db, tk_id, tk.ten_tk, from_date) if from_date else Decimal("0")
    out: list[dict] = []
    for g in items:
        delta = Decimal(g.so_tien) if g.loai == "thu" else -Decimal(g.so_tien)
        so_du += delta
        out.append({
            "id": g.id, "ngay": g.ngay, "tai_khoan_id": tk_id,
            "loai": g.loai, "so_tien": g.so_tien,
            "doi_tac": (g.noi_dung or g.mo_ta or "").strip() or None,
            "ghi_chu": g.nhan_vien_ten or g.ma_don or g.ghi_chu,
            "source_app": g.lien_quan, "source_doc_id": g.ref_id,
            "created_by": g.created_by, "created_at": g.created_at,
            "so_du_sau": so_du,
        })
    return out


@router.get("/{tk_id}/so-du", response_model=TaiKhoanSoDuOut)
def get_so_du(
    tk_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Tổng số dư TK (nguồn: `ketoan.so_quy`, xem docstring đầu file).

    `so_du` tôn trọng snapshot `SoDuDauKy` qua `so_quy_auto.so_du_hien_tai` —
    khớp với màn Sổ Quỹ và chặn-chi (`assert_du_chi`) dùng cùng hàm này.
    """
    tk = _ensure_tai_khoan(db, tk_id)
    sums = db.execute(
        select(
            func.coalesce(
                func.sum(case(
                    (SoQuy.loai == "thu", SoQuy.so_tien),
                    else_=0,
                )), 0,
            ).label("thu"),
            func.coalesce(
                func.sum(case(
                    (SoQuy.loai == "chi", SoQuy.so_tien),
                    else_=0,
                )), 0,
            ).label("chi"),
            func.count(SoQuy.id).label("n"),
        ).where(SoQuy.tai_khoan == tk.ten_tk)
    ).one()
    thu = Decimal(str(sums.thu or 0))
    chi = Decimal(str(sums.chi or 0))
    return TaiKhoanSoDuOut(
        tai_khoan_id=tk_id,
        so_du=so_du_hien_tai(db, tk.ten_tk),
        tong_thu=thu,
        tong_chi=chi,
        so_giao_dich=int(sums.n or 0),
    )


@router.post(
    "/{tk_id}/giao-dich",
    response_model=TaiKhoanNHGiaoDichOut,
    status_code=status.HTTP_201_CREATED,
)
def create_giao_dich(
    tk_id: int,
    body: TaiKhoanNHGiaoDichCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Manual ghi nhận thu/chi cho TK ngân hàng.

    Số dư tự động cập nhật vì dùng SUM(thu)-SUM(chi) — không cần ALTER cột so_du.
    """
    tk = _ensure_tai_khoan(db, tk_id)
    if body.loai not in ("thu", "chi"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "loai phải là 'thu' hoặc 'chi'",
        )
    obj = TaiKhoanNHGiaoDich(
        ngay=body.ngay, tai_khoan_id=tk_id, loai=body.loai,
        so_tien=body.so_tien, doi_tac=body.doi_tac, ghi_chu=body.ghi_chu,
        source_app=body.source_app, source_doc_id=body.source_doc_id,
        created_by=user.username,
    )
    db.add(obj)
    db.flush()

    # Phase 2 — optional journal entry generation
    if body.gen_journal:
        # TK đối ứng: TK trong danh mục hoặc TK con của tài khoản tiền (1111, 1121…)
        if not body.counter_account or body.counter_account not in danh_muc_tk(db):
            db.rollback()
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "gen_journal=true → cần truyền counter_account hợp lệ "
                "(411/421/711/811/...)",
            )
        cash_acc = tk_tien_cua(tk)
        if body.loai == "thu":
            no_acc, co_acc = cash_acc, body.counter_account
        else:
            no_acc, co_acc = body.counter_account, cash_acc
        post_journal(
            db, ngay=body.ngay,
            mo_ta=body.ghi_chu or f"Thu/chi TK {tk.ten_tk}",
            source_type=f"tk_nh_{body.loai}", source_id=str(obj.id),
            by_user=user.username,
            lines=[
                {"loai": "no", "account_code": no_acc,
                 "ref_table": "tai_khoan_nh" if no_acc == cash_acc else None,
                 "ref_id": tk.id if no_acc == cash_acc else None,
                 "so_tien": body.so_tien,
                 "ghi_chu": f"{tk.ten_tk}" if no_acc == cash_acc else None},
                {"loai": "co", "account_code": co_acc,
                 "ref_table": "tai_khoan_nh" if co_acc == cash_acc else None,
                 "ref_id": tk.id if co_acc == cash_acc else None,
                 "so_tien": body.so_tien,
                 "ghi_chu": f"{tk.ten_tk}" if co_acc == cash_acc else None},
            ],
        )

    db.commit()
    db.refresh(obj)
    log_action(
        db, app="ketoan", action="tknh_gd_create",
        user=user, request=request, resource=f"tai_khoan_nh_giao_dich:{obj.id}",
        payload={
            "tk_id": tk_id, "loai": body.loai,
            "so_tien": float(body.so_tien), "ngay": str(body.ngay),
            "gen_journal": body.gen_journal,
            "counter_account": body.counter_account,
        },
    )
    return obj


@router.delete("/giao-dich/{gd_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_giao_dich(
    gd_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Xoá 1 giao dịch (admin only)."""
    if user.role not in ("admin", "ceo"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Chỉ admin/ceo được xoá giao dịch TK",
        )
    obj = db.get(TaiKhoanNHGiaoDich, gd_id)
    if not obj:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Giao dịch không tồn tại",
        )
    payload = {
        "tk_id": obj.tai_khoan_id, "loai": obj.loai,
        "so_tien": float(obj.so_tien), "ngay": str(obj.ngay),
    }
    db.delete(obj)
    db.commit()
    log_action(
        db, app="ketoan", action="tknh_gd_delete",
        user=user, request=request, resource=f"tai_khoan_nh_giao_dich:{gd_id}",
        payload=payload,
    )
