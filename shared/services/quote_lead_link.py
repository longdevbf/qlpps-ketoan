"""Cross-app helpers — link a Báo Giá quote ↔ Marketing lead via Customer.

Dùng chung cho thread chat order-comment giữa Kinh Doanh, Mua Hàng, Marketing,
CSKH. Tất cả comment cross-app lưu vào `marketing.lead_comments` với prefix
``[BG <quote_number>]`` để cùng phân biệt theo từng đơn báo giá.

Pattern lazy-import (xem `shared.services.employees`) — caller pass `db`
session, model imports thực hiện bên trong hàm để tránh import vòng cross-app.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session


PREFIX_FMT = "[BG {qnum}]"


def quote_comment_prefix(quote_number: Optional[str], qid: Optional[int] = None) -> str:
    """Build prefix `[BG <qnum>]` cho comment cross-app.

    Fallback `qid-<id>` nếu không có quote_number — để comment từ quote chưa
    được gán number vẫn hoạt động.
    """
    qn = (quote_number or "").strip() or (f"qid-{qid}" if qid else "qid-unknown")
    return PREFIX_FMT.format(qnum=qn)


def _lead_exists(db: Session, lead_id: str) -> bool:
    """Verify lead_id thực sự tồn tại trong marketing.leads (chống orphan)."""
    if not lead_id:
        return False
    try:
        from marketing.app.models import Lead  # cross-app lazy
        return db.get(Lead, lead_id) is not None
    except Exception:
        return False


def resolve_customer_lead_id(
    db: Session, quote
) -> Tuple[Optional[int], Optional[str]]:
    """Look up customer + lead_id linked to a Báo Giá quote.

    Trả `(customer_id, lead_id)`. Nếu quote không có customer_id → `(None, None)`.
    Nếu customer không có lead_id (hoặc lead_id orphan, lead không còn) →
    `(customer_id, None)` để caller tự xử lý (auto-create / báo lỗi).
    """
    from baogia.app.models import Customer  # cross-app lazy

    if not getattr(quote, "customer_id", None):
        return None, None
    cust = db.get(Customer, quote.customer_id)
    if not cust:
        return None, None
    if cust.lead_id and _lead_exists(db, cust.lead_id):
        return cust.id, cust.lead_id
    return cust.id, None


def ensure_customer_lead(
    db: Session, quote, actor_username: str
) -> Tuple[Optional[int], Optional[str]]:
    """Như `resolve_customer_lead_id` nhưng AUTO-CREATE marketing.Lead nếu
    customer chưa link, rồi gán `customer.lead_id`.

    Reuse SDT-dedup: nếu marketing.leads đã có lead cùng SDT → link luôn lead
    đó vào customer thay vì tạo mới (tránh duplicate cross-app).

    Trả `(customer_id, lead_id)`. Nếu quote không có customer → `(None, None)`.
    Auto-create lead fail (vd marketing module chưa load) → trả `(cust.id, None)`
    để caller raise lỗi rõ ràng.

    2026-05-11: cũng auto-create Customer khi quote chưa có `customer_id` (case
    quote tạo từ form `/quote/new` với customer_name free-text — không qua flow
    MKT chuyển lead). Trước đây → return (None, None) → comment endpoint trả 400
    "Báo giá chưa gắn khách hàng".
    """
    from baogia.app.models import Customer  # cross-app lazy

    if not getattr(quote, "customer_id", None):
        ho_ten = (getattr(quote, "customer_name", None) or "").strip() or "(Khách chưa rõ tên)"
        sdt = (getattr(quote, "customer_phone", None) or "").strip() or None
        dia_chi = (getattr(quote, "customer_address", None) or "").strip() or None
        try:
            existing = None
            if sdt:
                existing = db.query(Customer).filter(Customer.sdt == sdt).first()
            if existing is None:
                existing = Customer(
                    ho_ten=ho_ten,
                    sdt=sdt,
                    dia_chi=dia_chi,
                    nguon="kinh-doanh",
                    trang_thai="Mới",
                    kd_nhan=actor_username,
                )
                db.add(existing)
                db.flush()
            quote.customer_id = existing.id
            db.flush()
            cust = existing
        except Exception:
            db.rollback()
            return None, None
    else:
        cust = db.get(Customer, quote.customer_id)
        if not cust:
            return None, None
    # Verify lead_id thật sự còn tồn tại — orphan FK gây fail FK violation
    # khi insert lead_comments (KH có lead_id trỏ tới lead đã bị xóa).
    if cust.lead_id and _lead_exists(db, cust.lead_id):
        return cust.id, cust.lead_id

    try:
        from marketing.app.models import Lead  # cross-app lazy
        from marketing.app.routers.leads import _next_lead_id

        # Reuse SDT-dedup logic của marketing
        sdt_raw = (cust.sdt or "").strip()
        if sdt_raw:
            existing = db.query(Lead).filter(Lead.sdt == sdt_raw).first()
            if existing is not None:
                cust.lead_id = existing.id
                db.commit()
                db.refresh(cust)
                return cust.id, cust.lead_id

        now = datetime.now(tz=timezone.utc)
        lead = Lead(
            id=_next_lead_id(db),
            ho_ten=cust.ho_ten,
            sdt=cust.sdt,
            email=cust.email,
            dia_chi=cust.dia_chi,
            nguon=cust.nguon or "kinh-doanh",
            nhom_hang=cust.nhom_hang,
            noi_dung=cust.noi_dung,
            mkt_phu_trach=cust.mkt_phu_trach,
            kd_nhan=cust.kd_nhan or actor_username,
            ngay_chuyen_kd=now,
            trang_thai="Đã chuyển KD",
            tien_trinh=cust.tien_trinh,
            ghi_chu=cust.ghi_chu,
            created_by=actor_username,  # ai trigger auto-create lead → ghi nhận
        )
        db.add(lead)
        db.flush()
        cust.lead_id = lead.id
        db.commit()
        db.refresh(cust)
        return cust.id, cust.lead_id
    except Exception:
        db.rollback()
        return cust.id, None


def role_to_phong_ban(role: Optional[str]) -> str:
    """Map JWT role → phong_ban label cho LeadComment.phong_ban.

    Cùng convention với baogia.quote_actions.add_order_comment để 2 app post
    cùng định dạng → FE filter/style nhất quán.
    """
    r = (role or "").lower()
    if r == "mkt":
        return "Marketing"
    if r == "kd":
        return "Kinh Doanh"
    if r == "cskh":
        return "CSKH"
    if r == "mh":
        return "Mua Hàng"
    if r in ("manager", "admin", "ceo", "assistant_ceo"):
        return "Quản lý"
    return r or "Khác"


def quote_by_ref_bao_gia(db: Session, quote_number: Optional[str]):
    """Lookup baogia.quotes theo quote_number (= PO.ref_bao_gia)."""
    if not quote_number:
        return None
    from baogia.app.models import Quote  # cross-app lazy

    qnum = quote_number.strip()
    if not qnum:
        return None
    return db.query(Quote).filter(Quote.quote_number == qnum).first()


# ============================================================================
# Marketing Lead ↔ Báo Giá Customer mirror sync
# ============================================================================

# Field gốc map 1:1 — copy thẳng sang Customer khi Lead update.
# tien_trinh & trang_thai chỉ propagate khi Lead có set (KD có thể đã đổi sau).
LEAD_TO_CUSTOMER_FIELDS = (
    "ho_ten", "sdt", "email", "dia_chi",
    "nguon", "nhom_hang", "noi_dung",
    "mkt_phu_trach", "kd_nhan",
    "trang_thai", "tien_trinh", "ghi_chu",
)


def upsert_customer_for_lead(db: Session, lead) -> Optional[int]:
    """Tạo (hoặc update nếu đã có) baogia.Customer khớp với marketing.Lead.

    Idempotent — gọi nhiều lần không tạo trùng. Trả `customer_id` hoặc None
    nếu fail (caller log + xử lý). KHÔNG raise — fail-soft để không cản
    lead create.
    """
    if lead is None or not lead.id:
        return None
    try:
        from baogia.app.models import Customer  # cross-app lazy

        existing = db.execute(
            select_stmt_for_customer_by_lead(lead.id)
        ).scalar_one_or_none()
        if existing is not None:
            # Update các field nguồn từ Lead — không override tien_trinh KD đã tự set
            for f in LEAD_TO_CUSTOMER_FIELDS:
                v = getattr(lead, f, None)
                if v is None:
                    continue
                # Tôn trọng tiến trình KD tự cập nhật bên báo giá — không ghi đè.
                # kd_nhan KHÔNG được bảo vệ ở đây: MKT chuyển/reassign KD ở Lead
                # phải luôn đồng bộ sang Customer, nếu không KD mới sẽ không
                # thấy KH này bên báo giá (bug báo cáo 2026-07-10).
                if f == "tien_trinh" and getattr(existing, f, None):
                    continue
                setattr(existing, f, v)
            existing.ngay_chuyen = (
                lead.ngay_chuyen_kd if lead.ngay_chuyen_kd else existing.ngay_chuyen
            )
            db.flush()
            return existing.id

        cust = Customer(
            lead_id=lead.id,
            ho_ten=lead.ho_ten,
            sdt=lead.sdt,
            email=lead.email,
            dia_chi=lead.dia_chi,
            nguon=lead.nguon,
            nhom_hang=lead.nhom_hang,
            noi_dung=lead.noi_dung,
            trang_thai=lead.trang_thai,
            mkt_phu_trach=lead.mkt_phu_trach,
            kd_nhan=lead.kd_nhan,
            ngay_chuyen=lead.ngay_chuyen_kd if lead.ngay_chuyen_kd else None,
            tien_trinh=lead.tien_trinh,
            ghi_chu=lead.ghi_chu,
        )
        db.add(cust)
        db.flush()
        return cust.id
    except Exception:
        return None


def select_stmt_for_customer_by_lead(lead_id: str):
    """Trả select statement Customer where lead_id = X (avoid model import cycle)."""
    from sqlalchemy import select
    from baogia.app.models import Customer
    return select(Customer).where(Customer.lead_id == lead_id)


def delete_customer_for_lead(db: Session, lead_id: str) -> dict:
    """Xóa baogia.Customer khớp với marketing.Lead.

    Quotes của customer giữ lại (set customer_id=NULL) để KD không mất lịch sử
    báo giá — chỉ unlink reference. Trả thông tin xóa để log.

    KHÔNG commit — caller tự commit cùng transaction lead delete để atomicity.
    """
    out = {"customer_id": None, "deleted_customer": False, "unlinked_quotes": 0}
    if not lead_id:
        return out
    try:
        from sqlalchemy import update
        from baogia.app.models import Customer, Quote

        cust = db.execute(
            select_stmt_for_customer_by_lead(lead_id)
        ).scalar_one_or_none()
        if cust is None:
            return out

        out["customer_id"] = cust.id
        # Unlink quotes (preserve quote rows — chỉ NULL FK)
        result = db.execute(
            update(Quote)
            .where(Quote.customer_id == cust.id)
            .values(customer_id=None)
        )
        out["unlinked_quotes"] = result.rowcount or 0

        # Xóa customer comments + customer comment images cascade nhờ FK ondelete
        # ở migration; nếu chưa thì vẫn có thể fail → caller catch.
        db.delete(cust)
        db.flush()
        out["deleted_customer"] = True
        return out
    except Exception:
        return out


def propagate_lead_update_to_customer(
    db: Session, lead, changed_fields: dict
) -> Optional[int]:
    """Khi Lead PATCH/PUT update các field, propagate sang Customer khớp lead_id.

    `changed_fields`: dict {field: new_value} — chỉ field thực sự đổi.
    Trả `customer_id` đã update, hoặc None nếu không có customer khớp.

    KHÔNG raise — fail-soft, caller log.
    """
    if lead is None or not lead.id or not changed_fields:
        return None
    # Chỉ quan tâm các field LEAD_TO_CUSTOMER_FIELDS
    relevant = {k: v for k, v in changed_fields.items() if k in LEAD_TO_CUSTOMER_FIELDS}
    if not relevant:
        return None
    try:
        cust = db.execute(
            select_stmt_for_customer_by_lead(lead.id)
        ).scalar_one_or_none()
        if cust is None:
            return None
        kd_moi = False
        for f, v in relevant.items():
            # `trang_thai` do baogia kiểm soát (Mới ↔ Đẩy lại ↔ Đã chuyển KD —
            # state machine riêng giữa MKT-chuyen-kd, KD-day-lai, KD-update);
            # KHÔNG cho propagate auto từ MKT update lead — tránh ghi đè sai.
            if f == "trang_thai":
                continue
            # Tôn trọng tiến trình KD tự cập nhật bên báo giá — không override.
            # kd_nhan KHÔNG được bảo vệ ở đây nữa: trước đây guard này chặn
            # luôn việc MKT đổi/reassign KD khác qua form sửa Lead một khi
            # Customer đã có kd_nhan (tức sau lần chuyển đầu tiên) — KD mới
            # được chọn sẽ không bao giờ thấy KH bên báo giá. `relevant` ở
            # đây chỉ chứa field THỰC SỰ đổi trên Lead (xem `diff` ở caller),
            # nên khi kd_nhan có mặt tức MKT vừa chọn KD khác — phải đồng bộ.
            if f == "tien_trinh" and getattr(cust, f, None):
                continue
            # Nếu đây là lần đầu gán kd_nhan qua PATCH/PUT lead (thay vì endpoint
            # chuyen_kd riêng) → cần ghi thêm metadata giao KD.
            if f == "kd_nhan" and v:
                kd_moi = True
            setattr(cust, f, v)
        if kd_moi:
            now = datetime.now(timezone.utc)
            if not getattr(cust, "ngay_chuyen", None):
                cust.ngay_chuyen = now
            if not getattr(cust, "kd_nhan_dau_tien", None):
                cust.kd_nhan_dau_tien = cust.kd_nhan
                cust.ngay_kd_nhan_dau_tien = now
            # Vượt state 'Mới' để filter baogia ("ẩn KH chưa chuyển KD") hiển thị được
            if (cust.trang_thai or "").strip().lower() in ("", "mới", "moi", "new", "mkt_nuoi"):
                cust.trang_thai = "Đã chuyển KD"
        db.flush()
        return cust.id
    except Exception:
        return None
