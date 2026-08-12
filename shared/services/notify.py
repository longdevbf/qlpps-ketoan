"""shared.services.notify — helper tạo notification + emit Redis cho SSE.

Sử dụng:
    from shared.services.notify import notify, notify_lead_new, ...

    notify_lead_new(db, lead, by=user.username)
    db.commit()  # caller phải commit; helper chỉ db.add (idempotent với rollback)

Manager (admin/ceo/assistant_ceo/manager) luôn nhận noti cho mọi event
business-level (theo quyết định 2026-05-07 của anh).
"""
from __future__ import annotations

import json
import logging
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.models import Notification, User

log = logging.getLogger(__name__)

MANAGER_ROLES = ("admin", "ceo", "assistant_ceo", "manager")


def _uname_to_name(db: Session, val: Optional[str]) -> str:
    """Resolve username → full_name. Fallback shared.users.full_name >
    hcns.employees.ho_ten > raw val.

    Dùng để hiển thị tên người trong noti thay vì mã NV (vd nv26015).
    Fail-soft: nếu lookup lỗi → trả val gốc để noti không bị mất content.
    """
    if not val:
        return ""
    v = str(val).strip()
    if not v:
        return ""
    # Nếu không có pattern nv\d+ → giả sử đã là tên (legacy data)
    import re as _re
    if not _re.fullmatch(r"nv\d{3,}", v.lower()):
        return v
    try:
        from sqlalchemy import text as _text
        row = db.execute(_text(
            "SELECT full_name FROM shared.users WHERE username = :u LIMIT 1"
        ), {"u": v}).first()
        if row and row[0]:
            return row[0]
        row = db.execute(_text(
            "SELECT ho_ten FROM hcns.employees WHERE username = :u LIMIT 1"
        ), {"u": v}).first()
        if row and row[0]:
            return row[0]
    except Exception as e:
        log.debug("_uname_to_name lookup failed for %s: %s", v, e)
    return v


def _redis_publish(channel: str, payload: dict) -> None:
    """Publish lên Redis cho SSE push. Fail-soft.

    Dùng `emit_event` của shared.events — tự prepend prefix `events:` →
    SSE subscribe(`notif:{username}`) sẽ nhận được khớp pattern.
    """
    try:
        from shared.events import emit_event
        emit_event(channel, payload)
    except Exception as e:
        log.debug("emit_event skip: %s", e)


def _webpush_send(db: Session, target_username: str, *, title: str,
                  message: Optional[str], url: Optional[str],
                  ref_type: Optional[str], ref_id: Optional[str],
                  extra: Optional[dict] = None) -> None:
    """Đẩy Web Push ra OS notification (FCM/APNs/Mozilla).

    Fail-soft toàn bộ — KHÔNG được throw exception ra caller (sẽ rollback noti row).
    Subscription bị 404/410 (Gone) → xoá khỏi DB để lần sau khỏi gửi nữa.
    """
    try:
        from shared.config import settings
        if not (settings.vapid_public_key and settings.vapid_private_key):
            return  # chưa config VAPID — bỏ qua im lặng
        try:
            from pywebpush import webpush, WebPushException
        except ImportError:
            log.debug("pywebpush not installed — skip web push")
            return

        from shared.models import PushSubscription, Notification

        subs = db.execute(
            select(PushSubscription).where(PushSubscription.username == target_username)
        ).scalars().all()
        if not subs:
            return

        # Đếm unread để set badge số
        from sqlalchemy import func as _func
        unread = db.execute(
            select(_func.count(Notification.id)).where(
                Notification.target_username == target_username,
                Notification.seen.is_(False),
            )
        ).scalar() or 0

        _pl = {
            "title": title[:120],
            "body": (message or "")[:200],
            "url": url or "/",
            "ref_type": ref_type,
            "ref_id": str(ref_id) if ref_id is not None else None,
            "badge": int(unread),
        }
        if extra:
            _pl.update(extra)
        payload = json.dumps(_pl, ensure_ascii=False)

        vapid_claims = {"sub": settings.vapid_subject}
        # PEM-format private key acceptable hơn raw cho pywebpush
        vapid_priv = settings.vapid_private_key

        gone_ids: list[int] = []
        for s in subs:
            try:
                webpush(
                    subscription_info={
                        "endpoint": s.endpoint,
                        "keys": {"p256dh": s.p256dh, "auth": s.auth},
                    },
                    data=payload,
                    vapid_private_key=vapid_priv,
                    vapid_claims=dict(vapid_claims),  # webpush mutates
                    ttl=60 * 60 * 24,
                )
            except WebPushException as e:
                code = getattr(e.response, "status_code", None) if e.response else None
                if code in (404, 410):
                    gone_ids.append(s.id)
                else:
                    log.debug("webpush fail (%s): %s", code, e)
            except Exception as e:
                log.debug("webpush unexpected: %s", e)

        if gone_ids:
            from sqlalchemy import delete as _delete
            db.execute(
                _delete(PushSubscription).where(PushSubscription.id.in_(gone_ids))
            )
    except Exception as e:
        log.debug("webpush dispatch skip: %s", e)


def get_managers(db: Session) -> list[str]:
    """Tất cả admin/ceo/assistant_ceo/manager còn active."""
    rows = db.execute(
        select(User.username)
        .where(User.role.in_(MANAGER_ROLES))
        .where(User.active.is_(True))
    ).scalars().all()
    return [u for u in rows if u]


def notify(
    db: Session,
    *,
    target: str,
    source_app: str,
    event_type: str,
    title: str,
    message: Optional[str] = None,
    ref_type: Optional[str] = None,
    ref_id: Optional[str] = None,
    url: Optional[str] = None,
    severity: str = "info",
    created_by: Optional[str] = None,
    publish: bool = True,
    webpush: bool = True,
) -> Optional[Notification]:
    """Tạo 1 noti row + publish Redis (cho SSE push). Caller phải db.commit().

    webpush=False → vẫn tạo row + SSE (chuông realtime) nhưng KHÔNG đẩy OS Web Push
    (dùng cho tin nhắn nhóm đông để tránh dội thông báo hệ điều hành).
    """
    if not target:
        return None
    n = Notification(
        target_username=target,
        source_app=source_app,
        event_type=event_type,
        title=title[:255],
        message=message,
        ref_type=ref_type,
        ref_id=str(ref_id) if ref_id is not None else None,
        url=url,
        severity=severity,
        created_by=created_by,
    )
    db.add(n)
    db.flush()  # cần id để publish
    if publish:
        _redis_publish(
            f"notif:{target}",
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "event_type": event_type,
                "source_app": source_app,
                "ref_type": ref_type,
                "ref_id": n.ref_id,
                "url": url,
                "severity": severity,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            },
        )
        # Web Push (OS-level notification + badge) — fail-soft, không break tx
        if webpush:
            _webpush_send(
                db, target,
                title=n.title, message=n.message, url=url,
                ref_type=ref_type, ref_id=n.ref_id,
            )
    return n


def notify_many(
    db: Session,
    targets: Iterable[str],
    *,
    exclude: Optional[Iterable[str]] = None,
    **kwargs,
) -> int:
    """Tạo noti cho nhiều user. Trả count."""
    excluded = set(filter(None, exclude or []))
    seen: set[str] = set()
    count = 0
    for u in targets:
        if not u or u in excluded or u in seen:
            continue
        seen.add(u)
        if notify(db, target=u, **kwargs):
            count += 1
    return count


# ─── Resolvers theo event ────────────────────────────────────────────────────
# Đây là logic "ai cần biết về event này". Tách riêng để 3 app gọi được.

# Public host map — dùng để build absolute URL cho noti, mỗi app 1 sub.
# Cho phép override qua env nếu deploy môi trường khác.
import os as _os
APP_HOST = {
    "marketing": _os.environ.get("HOST_MARKETING", "https://marketing.qlpps.com"),
    "baogia":    _os.environ.get("HOST_BAOGIA",    "https://baogia.qlpps.com"),
    "muahang":   _os.environ.get("HOST_MUAHANG",   "https://muahang.qlpps.com"),
}


def _lead_url(app: str, lead_id) -> str:
    """Absolute URL để click noti → mở đúng app + khách hàng/lead.

    - marketing: /?lead=<id>            → openDetail(lead) tự chạy
    - baogia:    /khach-hang?lead_id=<id> → page customers + auto open
    """
    host = APP_HOST.get(app, "")
    if app == "baogia":
        return f"{host}/khach-hang?lead_id={lead_id}"
    return f"{host}/?lead={lead_id}"


def _notify_lead_both(
    db: Session, lead, *,
    extra_baogia_targets: list = None,
    extra_marketing_targets: list = None,
    exclude: list,
    exclude_baogia: Optional[list] = None,
    event_type: str,
    title: str,
    message: str,
    severity: str = "info",
    created_by: str,
) -> int:
    """Tạo noti cho cả marketing bell + baogia bell — mỗi app URL absolute trỏ
    về subdomain tương ứng. KD log vào baogia thấy noti có link đến KH; MKT log
    vào marketing thấy noti có link đến lead. Manager log app nào cũng có
    noti app đó.

    exclude_baogia: nếu set thì dùng riêng cho baogia (không dùng exclude chung).
    """
    lead_id = getattr(lead, "id", None)
    common_targets = [
        getattr(lead, "mkt_phu_trach", None),
        getattr(lead, "kd_nhan", None),
        *get_managers(db),
    ]
    bg_exclude = exclude_baogia if exclude_baogia is not None else exclude
    n = 0
    # 1. Marketing bell
    n += notify_many(
        db, targets=common_targets + (extra_marketing_targets or []),
        exclude=exclude, source_app="marketing", event_type=event_type,
        title=title, message=message, ref_type="lead", ref_id=lead_id,
        url=_lead_url("marketing", lead_id), severity=severity,
        created_by=created_by,
    )
    # 2. Baogia bell (cùng nội dung, URL trỏ baogia)
    n += notify_many(
        db, targets=common_targets + (extra_baogia_targets or []),
        exclude=bg_exclude, source_app="baogia", event_type=event_type,
        title=title, message=message, ref_type="lead", ref_id=lead_id,
        url=_lead_url("baogia", lead_id), severity=severity,
        created_by=created_by,
    )
    return n


def notify_lead_new(db: Session, lead, by: str) -> int:
    """Lead mới — marketing bell loại creator; baogia bell include creator (họ cần biết để đi báo giá)."""
    return _notify_lead_both(
        db, lead,
        exclude=[by],          # marketing: không cần báo người vừa tạo
        exclude_baogia=[],     # baogia: include tất cả kể cả creator
        event_type="lead:new",
        title=f"Lead mới: {getattr(lead, 'ho_ten', '') or '(chưa có tên)'}",
        message=f"Nguồn: {getattr(lead, 'nguon', '') or '—'} · SĐT: {getattr(lead, 'sdt', '') or '—'}",
        created_by=by,
    )


def notify_lead_status(db: Session, lead, old: str, new: str, by: str) -> int:
    return _notify_lead_both(
        db, lead, exclude=[by], event_type="lead:status",
        title=f"Lead đổi tiến trình: {getattr(lead, 'ho_ten', '')}",
        message=f"{old or '—'} → {new or '—'}",
        created_by=by,
    )


def notify_lead_chuyen_kd(db: Session, lead, by: str) -> int:
    return _notify_lead_both(
        db, lead, exclude=[by], event_type="lead:chuyen_kd",
        title=f"Lead chuyển KD: {getattr(lead, 'ho_ten', '')}",
        message=f"KD nhận: {_uname_to_name(db, getattr(lead, 'kd_nhan', None)) or '—'}",
        severity="warning",
        created_by=by,
    )


def notify_lead_quan_tam_lai(db: Session, lead, by: str) -> int:
    """Khách CŨ quan tâm lại (inbox lại qua chatbot) — báo KD đang phụ trách +
    MKT + managers để follow-up ngay, KHÔNG phải tự dò danh sách khách hàng.
    Anh Quang 2026-07-14: fix 'số đẩy lên lại không hiện thông báo'."""
    return _notify_lead_both(
        db, lead, exclude=[by], event_type="lead:quan_tam_lai",
        title=f"🔔 Khách quan tâm lại: {getattr(lead, 'ho_ten', '') or '(chưa có tên)'}",
        message=f"Nguồn: {getattr(lead, 'nguon', '') or '—'} · SĐT: {getattr(lead, 'sdt', '') or '—'}",
        severity="warning",
        created_by=by,
    )


def notify_lead_comment(db: Session, lead, comment, by: str) -> int:
    """Comment mới ở lead — báo cho cả 2 owner (mkt + kd) trừ người vừa gửi."""
    snippet = (getattr(comment, "noi_dung", "") or "")[:120]
    return _notify_lead_both(
        db, lead, exclude=[by], event_type="lead:comment",
        title=f"💬 Tin nhắn mới ở lead: {getattr(lead, 'ho_ten', '')}",
        message=f"{getattr(comment, 'phong_ban', '') or 'NV'}: {snippet}"
                + ("…" if len(getattr(comment, "noi_dung", "") or "") > 120 else ""),
        created_by=by,
    )


def notify_quote_new(db: Session, quote, mkt_phu_trach: Optional[str], by: str) -> int:
    """Báo giá mới."""
    return notify_many(
        db,
        targets=[
            getattr(quote, "salesperson", None),
            mkt_phu_trach,
            *get_managers(db),
        ],
        exclude=[by],
        source_app="baogia",
        event_type="quote:new",
        title=f"Báo giá mới: {getattr(quote, 'quote_number', '')}",
        message=f"Tổng: {getattr(quote, 'tong_don', '') or '—'}",
        ref_type="quote",
        ref_id=getattr(quote, "id", None),
        url=f"/?quote_id={getattr(quote, 'id', '')}",
        created_by=by,
    )


def notify_quote_duyet(db: Session, quote, action: str, by: str) -> int:
    """Báo giá được duyệt/từ chối."""
    is_reject = (action or "").lower() in ("reject", "tu_choi", "denied")
    return notify_many(
        db,
        targets=[
            getattr(quote, "salesperson", None),
            getattr(quote, "created_by", None),
            *get_managers(db),
        ],
        exclude=[by],
        source_app="baogia",
        event_type="quote:duyet",
        title=(f"❌ Báo giá bị từ chối: {getattr(quote, 'quote_number', '')}"
               if is_reject else
               f"✅ Báo giá được duyệt: {getattr(quote, 'quote_number', '')}"),
        message=f"Bởi: {_uname_to_name(db, by) or '—'}",
        ref_type="quote",
        ref_id=getattr(quote, "id", None),
        url=f"/?quote_id={getattr(quote, 'id', '')}",
        severity="critical" if is_reject else "info",
        created_by=by,
    )


def notify_quote_comment(db: Session, quote, lead_id: Optional[str],
                         phong_ban: Optional[str], by: str) -> int:
    """Comment trên báo giá."""
    return notify_many(
        db,
        targets=[
            getattr(quote, "salesperson", None),
            getattr(quote, "created_by", None),
            *get_managers(db),
        ],
        exclude=[by],
        source_app="baogia",
        event_type="quote:comment",
        title=f"💬 Tin nhắn trên báo giá {getattr(quote, 'quote_number', '')}",
        message=f"Phòng: {phong_ban or '—'} · Bởi: {_uname_to_name(db, by) or '—'}",
        ref_type="quote",
        ref_id=getattr(quote, "id", None),
        url=f"/?quote_id={getattr(quote, 'id', '')}",
        created_by=by,
    )


def notify_order_new(db: Session, order, by: str) -> int:
    """Đơn mua mới (muahang)."""
    return notify_many(
        db,
        targets=[
            getattr(order, "nv_mua_hang", None),
            getattr(order, "kd_owner", None),  # nếu có; fail-soft
            *get_managers(db),
        ],
        exclude=[by],
        source_app="muahang",
        event_type="order:new",
        title=f"Đơn mua mới: {getattr(order, 'ten_don', '') or getattr(order, 'id', '')}",
        message=f"Ref BG: {getattr(order, 'ref_bao_gia', '') or '—'}",
        ref_type="order",
        ref_id=getattr(order, "id", None),
        url=f"/?order={getattr(order, 'id', '')}",
        created_by=by,
    )


def notify_order_status(db: Session, order, old: str, new: str, by: str) -> int:
    return notify_many(
        db,
        targets=[
            getattr(order, "nv_mua_hang", None),
            getattr(order, "kd_owner", None),
            getattr(order, "created_by", None),
            *get_managers(db),
        ],
        exclude=[by],
        source_app="muahang",
        event_type="order:status",
        title=f"Đơn đổi trạng thái: {getattr(order, 'ten_don', '') or getattr(order, 'id', '')}",
        message=f"{old or '—'} → {new or '—'}",
        ref_type="order",
        ref_id=getattr(order, "id", None),
        url=f"/?order={getattr(order, 'id', '')}",
        created_by=by,
    )


def notify_order_ready_to_ship(db: Session, order, by: str) -> int:
    """PO chuyển sang 'Đã có hàng' → báo Sale Admin để tạo lệnh vận chuyển.

    Target: user có role='sa' HOẶC apps chứa 'saleadmin' (active). Manager đã
    được notify_order_status cover; helper này chỉ thêm SA users.
    """
    from sqlalchemy import or_ as _or

    rows = db.execute(
        select(User.username)
        .where(User.active.is_(True))
        .where(_or(
            User.role == "sa",
            User.apps.any("saleadmin"),
        ))
    ).scalars().all()
    targets = [u for u in rows if u]
    if not targets:
        return 0
    return notify_many(
        db,
        targets=targets,
        exclude=[by],
        source_app="muahang",
        event_type="order:ready_to_ship",
        title=f"📦 Đơn sẵn sàng giao: {getattr(order, 'ten_don', '') or getattr(order, 'id', '')}",
        message=f"NV mua: {_uname_to_name(db, getattr(order, 'nv_mua_hang', None)) or '—'} · Ref BG: {getattr(order, 'ref_bao_gia', '') or '—'}",
        ref_type="order",
        ref_id=getattr(order, "id", None),
        url="/?tab=van-chuyen",
        severity="warning",
        created_by=by,
    )


def notify_quote_ttp_confirmed(db: Session, quote, po_id: Optional[str],
                                mh_target: Optional[str], by: str) -> int:
    """Baogia xác nhận đầy đủ 'thông tin phụ' — báo NV mua hàng phụ trách PO
    (nếu đã có PO link với quote) + managers. Cross-app: target xem ở app
    muahang → url phải absolute (khác domain nguồn baogia)."""
    host = APP_HOST.get("muahang", "")
    targets = [mh_target, *get_managers(db)] if po_id else list(get_managers(db))
    if not targets:
        return 0
    return notify_many(
        db,
        targets=targets,
        exclude=[by],
        source_app="baogia",
        event_type="quote:ttp_confirmed",
        title=f"✅ Đã xác nhận đầy đủ thông tin phụ: {getattr(quote, 'quote_number', '')}",
        message=f"Bởi: {_uname_to_name(db, by) or '—'}",
        ref_type="order" if po_id else "quote",
        ref_id=po_id or getattr(quote, "id", None),
        url=(f"{host}/?order={po_id}" if po_id else None),
        created_by=by,
    )


def notify_quote_ttp_missing(db: Session, quote, ly_do: str, by: str) -> int:
    """Muahang báo thiếu thông tin phụ — báo NV Kinh Doanh phụ trách báo giá
    + managers, xem ở app baogia (/duyet-don) → url absolute."""
    host = APP_HOST.get("baogia", "")
    targets = [getattr(quote, "salesperson", None), *get_managers(db)]
    return notify_many(
        db,
        targets=targets,
        exclude=[by],
        source_app="muahang",
        event_type="quote:ttp_missing",
        title=f"⚠️ Thiếu thông tin phụ: {getattr(quote, 'quote_number', '')}",
        message=f"Lý do: {ly_do or '—'}",
        ref_type="quote",
        ref_id=getattr(quote, "id", None),
        url=f"{host}/duyet-don?quote_id={getattr(quote, 'id', '')}",
        severity="warning",
        created_by=by,
    )


def notify_quote_ttp_ack(db: Session, quote, by: str) -> int:
    """Muahang xác nhận đã nhận đủ thông tin phụ — báo NV Kinh Doanh (đóng vòng
    lặp, không cần chủ động vào lại xem)."""
    host = APP_HOST.get("baogia", "")
    targets = [getattr(quote, "salesperson", None), *get_managers(db)]
    return notify_many(
        db,
        targets=targets,
        exclude=[by],
        source_app="muahang",
        event_type="quote:ttp_ack",
        title=f"✅ Mua Hàng đã xác nhận đủ thông tin: {getattr(quote, 'quote_number', '')}",
        message=f"Bởi: {_uname_to_name(db, by) or '—'}",
        ref_type="quote",
        ref_id=getattr(quote, "id", None),
        url=f"{host}/duyet-don?quote_id={getattr(quote, 'id', '')}",
        created_by=by,
    )


def notify_supplier_new(db: Session, supplier, by: str) -> int:
    return notify_many(
        db,
        targets=get_managers(db),
        exclude=[by],
        source_app="muahang",
        event_type="supplier:new",
        title=f"NCC mới: {getattr(supplier, 'name', '')}",
        ref_type="supplier",
        ref_id=getattr(supplier, "id", None),
        created_by=by,
    )
