"""calendar_sync — auto-create/update CalendarEvent từ business entities.

Helpers idempotent (source + source_ref_id là key):
    upsert_event_from_leave(db, leave_req)        → 'leave_request'
    upsert_event_from_directive(db, directive)    → 'directive'
    upsert_event_from_dao_tao(db, session)        → 'dao_tao_session'
    delete_event_by_source(db, source, ref_id)

Tất cả fail-soft: try/except, log warning, không break tx của caller. Caller
chịu trách nhiệm commit. Import lazy ở callsite để tránh circular import.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select, text as sql_text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# Múi giờ VN (Asia/Ho_Chi_Minh = UTC+7) — dùng offset cố định để khỏi phụ
# thuộc zoneinfo trên môi trường không có tzdata.
_VN_TZ = timezone(timedelta(hours=7))

_PRIORITY_COLOR = {
    "low":  "#3b82f6",
    "med":  "#f59e0b",
    "high": "#dc2626",
}


# ─── Internal helpers ────────────────────────────────────────────────────────

def _CE():
    """Lazy import CalendarEvent + EventParticipant để tránh circular."""
    from shared.models.calendar_event import CalendarEvent, EventParticipant
    return CalendarEvent, EventParticipant


def _to_vn_dt(d: Any, t: time) -> datetime:
    """Combine date|datetime + time → tz-aware datetime ở VN tz."""
    if isinstance(d, datetime):
        # Drop time portion, dùng `t` thay vào
        d = d.date()
    return datetime.combine(d, t, tzinfo=_VN_TZ)


def _find_event(db: Session, source: str, ref_id: str):
    CalendarEvent, _ = _CE()
    return db.execute(
        select(CalendarEvent)
        .where(CalendarEvent.source == source)
        .where(CalendarEvent.source_ref_id == ref_id)
    ).scalars().first()


def _apply_participants(db: Session, event_id: int, usernames: list[str]) -> None:
    """Replace toàn bộ participants của event = list usernames mới (loại trùng)."""
    _, EventParticipant = _CE()
    # Xoá hết participants cũ
    db.query(EventParticipant).filter(EventParticipant.event_id == event_id).delete(
        synchronize_session=False
    )
    seen: set[str] = set()
    for u in usernames or []:
        u = (u or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        db.add(EventParticipant(event_id=event_id, username=u, role="attendee"))


def _employees_in_phong_ban(db: Session, phong_ban: Optional[str]) -> list[str]:
    """Trả về list username NV cùng phong_ban (đang làm). Fail-soft → []."""
    if not phong_ban:
        return []
    try:
        rows = db.execute(sql_text(
            "SELECT username FROM hcns.employees "
            "WHERE phong_ban = :pb AND username IS NOT NULL AND username != '' "
            "  AND trang_thai IN ('active', 'Đang làm')"
        ), {"pb": phong_ban}).all()
        return [r[0] for r in rows if r and r[0]]
    except Exception as exc:
        log.warning("calendar_sync._employees_in_phong_ban failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return []


# ─── Public helpers ──────────────────────────────────────────────────────────

def delete_event_by_source(db: Session, source: str, ref_id: str) -> bool:
    """Xoá event auto-created theo (source, ref_id). Idempotent → True nếu có xoá."""
    try:
        ev = _find_event(db, source, ref_id)
        if not ev:
            return False
        db.delete(ev)
        db.flush()
        return True
    except Exception as exc:
        log.warning("calendar_sync.delete_event_by_source(%s,%s) failed: %s",
                    source, ref_id, exc)
        return False


def upsert_event_from_leave(db: Session, leave_req: Any) -> Optional[int]:
    """LeaveRequest 'da_duyet' → create/update event 'Nghỉ phép'.

    - title: '🏖️ Nghỉ phép: {loai_nghi}'
    - all_day: True, event_type='personal', color='#ef4444'
    - source='leave_request', source_ref_id=str(id)
    - Trạng thái != 'da_duyet' → delete event.
    """
    if leave_req is None or getattr(leave_req, "id", None) is None:
        return None
    ref_id = str(leave_req.id)
    try:
        trang_thai = getattr(leave_req, "trang_thai", None)
        if trang_thai != "da_duyet":
            delete_event_by_source(db, "leave_request", ref_id)
            return None

        owner = getattr(leave_req, "username", None) or ""
        if not owner:
            return None

        loai_nghi = getattr(leave_req, "loai_nghi", "") or ""
        ngay_bd = getattr(leave_req, "ngay_bat_dau", None)
        ngay_kt = getattr(leave_req, "ngay_ket_thuc", None) or ngay_bd
        if not ngay_bd:
            return None
        start_dt = _to_vn_dt(ngay_bd, time(0, 0, 0))
        end_dt   = _to_vn_dt(ngay_kt, time(23, 59, 0))

        ly_do = getattr(leave_req, "ly_do", None) or ""
        ho_ten = getattr(leave_req, "ho_ten", None) or owner
        title = f"🏖️ Nghỉ phép: {loai_nghi}"
        desc  = f"{ho_ten} xin nghỉ ({loai_nghi}).\nLý do: {ly_do}"

        CalendarEvent, _ = _CE()
        ev = _find_event(db, "leave_request", ref_id)
        if ev is None:
            ev = CalendarEvent(
                owner_username=owner,
                title=title,
                description=desc,
                start_dt=start_dt,
                end_dt=end_dt,
                all_day=True,
                event_type="personal",
                color="#ef4444",
                source="leave_request",
                source_ref_id=ref_id,
                reminder_minutes=None,
            )
            db.add(ev)
        else:
            ev.owner_username = owner
            ev.title = title
            ev.description = desc
            ev.start_dt = start_dt
            ev.end_dt = end_dt
            ev.all_day = True
            ev.event_type = "personal"
            ev.color = "#ef4444"
        db.flush()
        return ev.id
    except Exception as exc:
        log.warning("calendar_sync.upsert_event_from_leave(id=%s) failed: %s",
                    ref_id, exc)
        return None


def upsert_event_from_directive(db: Session, directive: Any) -> Optional[int]:
    """Directive có due_date → event deadline cho directive.to_user.

    - title: '📋 Deadline: {title}'
    - start_dt: due_date 17:00 - 30 min = 16:30, end_dt: due_date 17:00 (EOD)
    - color theo priority (low/med/high)
    - source='directive', source_ref_id=str(id)
    - status != 'open' hoặc due_date null → delete event.
    """
    if directive is None or getattr(directive, "id", None) is None:
        return None
    ref_id = str(directive.id)
    try:
        status = getattr(directive, "status", None)
        due_date = getattr(directive, "due_date", None)
        if status != "open" or not due_date:
            delete_event_by_source(db, "directive", ref_id)
            return None

        owner = getattr(directive, "to_user", None) or ""
        if not owner:
            return None

        title_src = getattr(directive, "title", "") or ""
        title = f"📋 Deadline: {title_src}"
        body = getattr(directive, "body", None) or ""
        from_user = getattr(directive, "from_user", "") or ""
        priority = (getattr(directive, "priority", "med") or "med").lower()
        color = _PRIORITY_COLOR.get(priority, "#f59e0b")
        desc = f"Người giao: {from_user} | Ưu tiên: {priority}\n{body}".strip()

        # Treat due_date as end-of-business-day 17:00 VN
        end_dt = _to_vn_dt(due_date, time(17, 0, 0))
        start_dt = end_dt - timedelta(minutes=30)

        CalendarEvent, _ = _CE()
        ev = _find_event(db, "directive", ref_id)
        if ev is None:
            ev = CalendarEvent(
                owner_username=owner,
                title=title,
                description=desc,
                start_dt=start_dt,
                end_dt=end_dt,
                all_day=False,
                event_type="personal",
                color=color,
                source="directive",
                source_ref_id=ref_id,
                reminder_minutes=30,
            )
            db.add(ev)
        else:
            ev.owner_username = owner
            ev.title = title
            ev.description = desc
            ev.start_dt = start_dt
            ev.end_dt = end_dt
            ev.all_day = False
            ev.event_type = "personal"
            ev.color = color
            if ev.reminder_minutes is None:
                ev.reminder_minutes = 30
        db.flush()
        return ev.id
    except Exception as exc:
        log.warning("calendar_sync.upsert_event_from_directive(id=%s) failed: %s",
                    ref_id, exc)
        return None


def upsert_event_from_dao_tao(db: Session, session: Any) -> Optional[int]:
    """DaoTaoSession.ngay → event share toàn phòng (event_type='shared').

    - title: '🎓 Đào tạo: {ten}' (model dùng field `ten`; fallback `tieu_de`)
    - start_dt: session.ngay 08:00, end_dt: session.ngay 17:00
    - color: '#ec4899'
    - source='dao_tao_session', source_ref_id=str(id)
    - Participants: tất cả NV cùng phong_ban (query hcns.employees).
    - Nếu ngay null → delete event.
    """
    if session is None or getattr(session, "id", None) is None:
        return None
    ref_id = str(session.id)
    try:
        ngay = getattr(session, "ngay", None)
        if not ngay:
            delete_event_by_source(db, "dao_tao_session", ref_id)
            return None

        # Tên session: model marketing dùng `ten`, một số chỗ V1 có thể `tieu_de`
        ten = getattr(session, "ten", None) or getattr(session, "tieu_de", "") or ""
        giang_vien = getattr(session, "giang_vien", None) or ""
        phong_ban = getattr(session, "phong_ban", None) or ""
        mo_ta = getattr(session, "mo_ta", None) or ""
        created_by = getattr(session, "created_by", "") or ""
        owner = created_by or "system"

        title = f"🎓 Đào tạo: {ten}"
        desc_parts = []
        if giang_vien:
            desc_parts.append(f"Giảng viên: {giang_vien}")
        if phong_ban:
            desc_parts.append(f"Phòng ban: {phong_ban}")
        if mo_ta:
            desc_parts.append(mo_ta)
        desc = "\n".join(desc_parts)

        start_dt = _to_vn_dt(ngay, time(8, 0, 0))
        end_dt   = _to_vn_dt(ngay, time(17, 0, 0))

        CalendarEvent, _ = _CE()
        ev = _find_event(db, "dao_tao_session", ref_id)
        if ev is None:
            ev = CalendarEvent(
                owner_username=owner,
                title=title,
                description=desc,
                start_dt=start_dt,
                end_dt=end_dt,
                all_day=False,
                event_type="shared",
                color="#ec4899",
                source="dao_tao_session",
                source_ref_id=ref_id,
                reminder_minutes=60,
            )
            db.add(ev)
            db.flush()
        else:
            ev.owner_username = owner
            ev.title = title
            ev.description = desc
            ev.start_dt = start_dt
            ev.end_dt = end_dt
            ev.all_day = False
            ev.event_type = "shared"
            ev.color = "#ec4899"
            db.flush()

        # Participants: tất cả NV cùng phong_ban + created_by (organizer)
        usernames = _employees_in_phong_ban(db, phong_ban)
        if created_by and created_by not in usernames:
            usernames.append(created_by)
        try:
            _apply_participants(db, ev.id, usernames)
            db.flush()
        except Exception as exc:
            log.warning("calendar_sync.upsert_event_from_dao_tao participants failed: %s", exc)
        return ev.id
    except Exception as exc:
        log.warning("calendar_sync.upsert_event_from_dao_tao(id=%s) failed: %s",
                    ref_id, exc)
        return None
