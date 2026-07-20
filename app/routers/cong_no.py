"""CongNo API — CRUD + POST /{id}/tra (cập nhật trạng thái trả nợ)."""
from datetime import date as date_cls
from decimal import Decimal
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import CongNo
from ..schemas import CongNoCreate, CongNoUpdate, CongNoOut, CongNoTraBody
from ..services import next_cong_no_id
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


class CongNoImportBody(BaseModel):
    source: str = Field(..., pattern="^(baogia|muahang)$")
    from_date: Optional[date_cls] = None
    to_date: Optional[date_cls] = None


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
    limit: int = 500,
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
        stmt = stmt.where(CongNo.doi_tac.ilike(f"%{doi_tac}%"))
    if q:
        kw = f"%{q}%"
        stmt = stmt.where(
            or_(
                CongNo.doi_tac.ilike(kw),
                CongNo.ma_don.ilike(kw),
            )
        )
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


@router.post("/import")
def import_cong_no(
    body: CongNoImportBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
) -> dict[str, Any]:
    """Bulk import công nợ từ baogia.quotes (phai_thu) hoặc muahang.purchase_orders (phai_tra).

    Idempotent qua field `ref_id` — record có ref_id trùng sẽ skip.

    Body:
        - source: 'baogia' → quotes duyet_status='approved' tong_don > 0 → cong_no(loai='phai_thu')
        - source: 'muahang' → POs status='Hoàn Thành' với selected_ncc + ncc_totals → cong_no(loai='phai_tra')
        - from_date / to_date: lọc theo created_at (optional)

    Trả: {imported: N, skipped: M, source, items: [...]}.
    """
    imported = skipped = 0
    sample: list[dict[str, Any]] = []

    if body.source == "baogia":
        from baogia.app.models import Quote  # lazy cross-app
        stmt = (
            select(Quote)
            .where(Quote.duyet_status == "approved")
            .where(Quote.tong_don.is_not(None))
            .where(Quote.tong_don > 0)
        )
        if body.from_date:
            stmt = stmt.where(Quote.created_at >= body.from_date)
        if body.to_date:
            stmt = stmt.where(Quote.created_at < body.to_date)

        for q in db.execute(stmt).scalars().all():
            ref_id = f"BG-{q.quote_number}" if q.quote_number else f"BG-{q.id}"
            existing = db.execute(
                select(CongNo).where(CongNo.ref_id == ref_id)
            ).scalar_one_or_none()
            if existing:
                skipped += 1
                continue
            so_tien = Decimal(q.tong_don or 0)
            deposit = Decimal(q.deposit or 0)
            cid = next_cong_no_id(db)
            obj = CongNo(
                id=cid,
                ngay=(q.created_at.date() if q.created_at else date_cls.today()),
                doi_tac=q.customer_name or "(unknown)",
                so_tien=so_tien,
                da_tra=deposit if deposit > 0 and deposit < so_tien else Decimal("0"),
                loai="phai_thu",
                loai_chi_tiet="Công Nợ Khách Hàng",
                ma_don=q.quote_number,
                ref_id=ref_id,
                ref_source="baogia",
                han_thanh_toan=None,
                trang_thai="chua_tra",
                ghi_chu=f"Auto-import từ báo giá {q.quote_number} (NV: {q.salesperson or '—'})",
                created_by=user.username,
            )
            db.add(obj)
            db.flush()  # nhận id rồi commit cuối
            imported += 1
            if len(sample) < 5:
                sample.append({
                    "id": cid, "doi_tac": obj.doi_tac, "so_tien": str(obj.so_tien),
                    "ref_id": ref_id, "ma_don": obj.ma_don,
                })

    elif body.source == "muahang":
        from muahang.app.models import PurchaseOrder, Supplier  # lazy cross-app
        stmt = (
            select(PurchaseOrder)
            .where(PurchaseOrder.status.in_(["Hoàn Thành", "Đã giao"]))
        )
        if body.from_date:
            stmt = stmt.where(PurchaseOrder.created_at >= body.from_date)
        if body.to_date:
            stmt = stmt.where(PurchaseOrder.created_at < body.to_date)

        # Cache supplier names
        suppliers = db.execute(select(Supplier.id, Supplier.name)).all()
        ncc_name_by_id = {s.id: s.name for s in suppliers}

        for po in db.execute(stmt).scalars().all():
            ref_id = f"MH-{po.id}"
            existing = db.execute(
                select(CongNo).where(CongNo.ref_id == ref_id)
            ).scalar_one_or_none()
            if existing:
                skipped += 1
                continue

            totals = po.ncc_totals or {}
            names = po.ncc_names or {}
            sel_id = po.selected_ncc_id or po.comparison_best_ncc

            so_tien = Decimal("0")
            ncc_name = "(unknown)"
            if sel_id and str(sel_id) in totals:
                so_tien = Decimal(str(totals[str(sel_id)] or 0))
                ncc_name = (
                    names.get(str(sel_id))
                    or ncc_name_by_id.get(sel_id)
                    or str(sel_id)
                )
            elif totals:
                first_id = next(iter(totals.keys()))
                so_tien = Decimal(str(totals[first_id] or 0))
                ncc_name = (
                    names.get(first_id)
                    or ncc_name_by_id.get(first_id)
                    or first_id
                )

            if so_tien <= 0:
                # Bỏ PO không có tổng tiền
                skipped += 1
                continue

            cid = next_cong_no_id(db)
            obj = CongNo(
                id=cid,
                ngay=(po.created_at.date() if po.created_at else date_cls.today()),
                doi_tac=ncc_name,
                so_tien=so_tien,
                da_tra=Decimal("0"),
                loai="phai_tra",
                loai_chi_tiet="Công Nợ NCC",
                ma_don=po.id,
                ref_id=ref_id,
                ref_source="muahang",
                han_thanh_toan=None,
                trang_thai="chua_tra",
                ghi_chu=f"Auto-import từ PO {po.id} ({po.ten_don or ''})".strip(),
                created_by=user.username,
            )
            db.add(obj)
            db.flush()
            imported += 1
            if len(sample) < 5:
                sample.append({
                    "id": cid, "doi_tac": obj.doi_tac, "so_tien": str(obj.so_tien),
                    "ref_id": ref_id, "ma_don": obj.ma_don,
                })

    db.commit()

    log_action(
        db, app="ketoan", action="import_cong_no", user=user, request=request,
        resource=f"cong_no:bulk:{body.source}",
        payload={"imported": imported, "skipped": skipped, "source": body.source},
    )

    return {
        "source": body.source,
        "imported": imported,
        "skipped": skipped,
        "from_date": body.from_date.isoformat() if body.from_date else None,
        "to_date": body.to_date.isoformat() if body.to_date else None,
        "items": sample,  # mẫu 5 record đầu
    }


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
    user: Annotated[JWTPayload, _AUTH],
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
        resource=f"cong_no:{cid}", payload=fields,
    )
    return obj


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
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(CongNo, cid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CongNo không tồn tại")
    # Xóa cascade sổ quỹ liên quan (ref_id chứa cid)
    from sqlalchemy import delete as sql_delete
    db.execute(
        sql_delete(SoQuy).where(
            SoQuy.lien_quan == "cong_no",
            SoQuy.ref_id.ilike(f"%{cid}%"),
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
        default=None,
        description="['muahang','baogia','saleadmin']. Default: tất cả."
    ),
):
    """Pull công nợ từ 3 app:
    - **muahang**: purchase_orders đã chốt → phải trả NCC
    - **baogia**: quotes đã duyệt → phải thu KH
    - **saleadmin**: vanchuyen → phải trả ĐVVC + phải thu KH (qua DVVC)

    Idempotent qua UNIQUE (ref_source, ref_id) — chạy lại không tạo trùng,
    chỉ update so_tien nếu thay đổi (vd PO sửa lại).
    """
    from sqlalchemy import text as _t

    selected = set(sources or ["muahang", "baogia", "saleadmin"])
    result = {
        "muahang": {"created": 0, "updated": 0, "skipped": 0, "errors": []},
        "baogia": {"created": 0, "updated": 0, "skipped": 0, "errors": []},
        "saleadmin_pt": {"created": 0, "updated": 0, "skipped": 0, "errors": []},
        "saleadmin_pn": {"created": 0, "updated": 0, "skipped": 0, "errors": []},
    }

    def _upsert(ref_source: str, ref_id: str, fields: dict) -> str:
        """Upsert vào ketoan.cong_no qua (ref_source, ref_id). Trả 'created' / 'updated' / 'skipped'.

        fields hỗ trợ key bổ sung `da_tra_nguon` — số tiền đã trả ghi nhận từ app nguồn
        (vd baogia.deposit). Dùng để khởi tạo da_tra khi tạo mới, và cập nhật nếu kế toán
        chưa ghi nhận thủ công (da_tra == 0).
        """
        da_tra_nguon = Decimal(str(fields.pop("da_tra_nguon", 0) or 0))
        existing = db.execute(
            select(CongNo).where(
                CongNo.ref_source == ref_source,
                CongNo.ref_id == ref_id,
            )
        ).scalar_one_or_none()
        if existing:
            changed = False
            new_so_tien = Decimal(str(fields.get("so_tien", 0)))
            if existing.so_tien != new_so_tien and (existing.da_tra or 0) <= new_so_tien:
                existing.so_tien = new_so_tien
                changed = True
            # Cập nhật da_tra từ nguồn nếu kế toán chưa ghi nhận thủ công
            if da_tra_nguon > 0 and (existing.da_tra or Decimal("0")) == Decimal("0"):
                existing.da_tra = da_tra_nguon
                so_tien_cur = Decimal(str(existing.so_tien or 0))
                if da_tra_nguon >= so_tien_cur > 0:
                    existing.trang_thai = "da_tra"
                changed = True
            if fields.get("doi_tac") and changed:
                existing.doi_tac = fields["doi_tac"]
            if fields.get("ghi_chu") and changed:
                existing.ghi_chu = fields["ghi_chu"]
            if changed:
                db.commit()
                return "updated"
            return "skipped"
        # Tạo mới — lấy da_tra từ nguồn nếu có
        da_tra_init = da_tra_nguon
        so_tien_new = Decimal(str(fields.get("so_tien", 0)))
        trang_thai_init = "da_tra" if da_tra_init >= so_tien_new > 0 else "chua_tra"
        cid = next_cong_no_id(db)
        rec = CongNo(
            id=cid,
            ngay=fields["ngay"],
            doi_tac=fields["doi_tac"],
            so_tien=so_tien_new,
            da_tra=da_tra_init,
            loai=fields["loai"],
            loai_chi_tiet=fields.get("loai_chi_tiet"),
            ma_don=fields.get("ma_don"),
            ref_id=ref_id,
            ref_source=ref_source,
            han_thanh_toan=fields.get("han_thanh_toan"),
            trang_thai=trang_thai_init,
            ghi_chu=fields.get("ghi_chu"),
            created_by=user.username,
        )
        db.add(rec)
        db.commit()
        return "created"

    # ── 1. MUAHANG → phải trả NCC ───────────────────────────────────────────
    # REFACTOR 27/05/26: Đơn nguồn logic — delegate sang service
    # `create_cong_no_list_from_order` (cong_no_from_order.py). Service này:
    #   - Resolve TẤT CẢ NCC con trong combo (không chỉ moc/son như code cũ)
    #   - Dùng ref_id format `MH-{po_id}-NCC{ncc_id}` (UNIQUE INDEX bảo vệ)
    #   - Idempotent: skip nếu đã có
    #
    # Code cũ tạo ref_id `{po_id}:{ncc_id}` + chỉ 2 NCC trong combo (moc+son) →
    # gây trùng + thiếu NCC con (đệm/kính). Đã cleanup 20 dup rows 27/05.
    if "muahang" in selected:
        try:
            from ketoan.app.services.cong_no_from_order import (
                create_cong_no_list_from_order, CongNoFromOrderError,
            )
            po_ids = db.execute(_t("""
                SELECT id FROM muahang.purchase_orders
                WHERE selected_ncc_id IS NOT NULL
                  AND status IN ('Đã có hàng','Hoàn Thành')
            """)).scalars().all()
            for po_id in po_ids:
                try:
                    created_list = create_cong_no_list_from_order(
                        db, str(po_id),
                        created_by="bulk-resync",
                        require_terminal=False,  # filter status đã làm ở query trên
                        commit=False,
                    )
                    result["muahang"]["created"] += len(created_list)
                except CongNoFromOrderError as ex:
                    if ex.code == "duplicate":
                        result["muahang"]["skipped"] += 1
                    else:
                        result["muahang"]["errors"].append(f"po:{po_id}: {ex.message}")
                except Exception as ex:
                    db.rollback()
                    result["muahang"]["errors"].append(f"po:{po_id}: {ex}")
            db.commit()
        except Exception as ex:
            db.rollback()
            result["muahang"]["errors"].append(f"query: {ex}")

    # ── 2. BAOGIA → phải thu KH ─────────────────────────────────────────────
    if "baogia" in selected:
        try:
            rows = db.execute(_t("""
                SELECT q.id, q.quote_number, q.customer_name, q.duyet_luc, q.created_at,
                       COALESCE(q.tong_don, 0) AS tong_don,
                       COALESCE(q.deposit, 0) AS deposit
                FROM baogia.quotes q
                WHERE q.duyet_status = 'approved'
                  AND COALESCE(q.tong_don, 0) > 0
            """)).mappings().all()
            for r in rows:
                try:
                    deposit = float(r.get("deposit") or 0)
                    tong_don = float(r["tong_don"])
                    action = _upsert("baogia_quote", str(r["id"]), {
                        "loai": "phai_thu",
                        "ngay": (r["duyet_luc"] or r["created_at"]).date() if (r["duyet_luc"] or r["created_at"]) else date_cls.today(),
                        "doi_tac": r["customer_name"] or "(KH chưa rõ)",
                        "so_tien": tong_don,
                        "da_tra_nguon": deposit if 0 < deposit < tong_don else 0,
                        "ma_don": r["quote_number"],
                        "loai_chi_tiet": "bao_gia_da_duyet",
                        "ghi_chu": f"Báo giá đã duyệt {r['quote_number']}",
                    })
                    result["baogia"][action] += 1
                except Exception as ex:
                    db.rollback()
                    result["baogia"]["errors"].append(f"quote:{r.get('id')}: {ex}")
        except Exception as ex:
            db.rollback()
            result["baogia"]["errors"].append(f"query: {ex}")

    # ── 3. SALEADMIN → phải trả ĐVVC + phải thu KH (qua DVVC) ───────────────
    if "saleadmin" in selected:
        try:
            rows = db.execute(_t("""
                SELECT id, ma_vh, ma_don, ten_kh, don_vi_vc, ngay_giao, created_at,
                       COALESCE(chi_phi_vc, 0) AS chi_phi_vc,
                       COALESCE(da_tra_dvvc, 0) AS da_tra_dvvc,
                       COALESCE(tien_thu_ho, 0) AS tien_thu_ho,
                       COALESCE(dvvc_da_thu, 0) AS dvvc_da_thu,
                       trang_thai
                FROM saleadmin.vanchuyen
                WHERE trang_thai NOT IN ('Đã hủy', 'Hủy')
            """)).mappings().all()
            for r in rows:
                try:
                    ngay = (r["ngay_giao"] or (r["created_at"].date() if r["created_at"] else date_cls.today()))
                    # 3a. Phải trả ĐVVC (cước vận chuyển còn nợ)
                    no_dvvc = float(r["chi_phi_vc"]) - float(r["da_tra_dvvc"])
                    ma_bg = r["ma_don"] or ""   # BG quote number từ saleadmin.vanchuyen
                    if no_dvvc > 0:
                        action = _upsert("saleadmin_vc_phai_tra", str(r["id"]), {
                            "loai": "phai_tra",
                            "ngay": ngay,
                            "doi_tac": r["don_vi_vc"] or "(ĐVVC chưa rõ)",
                            "so_tien": no_dvvc,
                            "ma_don": ma_bg,
                            "loai_chi_tiet": "vanchuyen_dvvc",
                            "ghi_chu": f"Cước VC {r['ma_vh']}" + (f" — đơn {ma_bg}" if ma_bg else ""),
                        })
                        result["saleadmin_pt"][action] += 1
                    # 3b. Phải thu KH (qua DVVC: KH trả cho DVVC nhưng DVVC chưa chuyển về)
                    pn_kh = float(r["tien_thu_ho"]) - float(r["dvvc_da_thu"])
                    if pn_kh > 0:
                        action = _upsert("saleadmin_vc_phai_thu", str(r["id"]), {
                            "loai": "phai_thu",
                            "ngay": ngay,
                            "doi_tac": r["ten_kh"] or "(KH chưa rõ)",
                            "so_tien": pn_kh,
                            "ma_don": ma_bg,
                            "loai_chi_tiet": "vanchuyen_kh",
                            "ghi_chu": f"Thu hộ KH {r['ma_vh']}" + (f" — đơn {ma_bg}" if ma_bg else ""),
                        })
                        result["saleadmin_pn"][action] += 1
                except Exception as ex:
                    db.rollback()
                    result["saleadmin_pt"]["errors"].append(f"vc:{r.get('id')}: {ex}")
        except Exception as ex:
            db.rollback()
            result["saleadmin_pt"]["errors"].append(f"query: {ex}")

    log_action(
        db, app="ketoan", action="sync_cong_no", user=user, request=request,
        resource="cong_no:sync", payload={"sources": list(selected), "result": result},
    )

    total_created = sum(r["created"] for r in result.values())
    total_updated = sum(r["updated"] for r in result.values())
    return {
        "ok": True,
        "summary": {
            "tao_moi": total_created,
            "cap_nhat": total_updated,
            "bo_qua": sum(r["skipped"] for r in result.values()),
            "loi": sum(len(r["errors"]) for r in result.values()),
        },
        "detail": result,
    }
