"""Lịch Làm Việc — shared router mount mọi app QLPPS.

Cùng table `shared.calendar_events` + `shared.event_participants`. User tạo
event cá nhân, mời thành viên, response invitation, query conflicts.

Endpoints (mount /api/calendar):
  GET    /events?start=&end=&include_shared=true
  POST   /events
  GET    /events/{id}
  PUT    /events/{id}
  DELETE /events/{id}
  POST   /events/{id}/invite
  POST   /events/{id}/respond
  GET    /conflicts?start=&end=
  GET    /events/by-source/{source}/{ref_id}

RBAC: mọi endpoint cần current_user. Owner xem/sửa lịch của mình; participant
xem lịch invite. Admin/CEO/assistant_ceo bypass khi DELETE.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal, Optional

import jwt as _jwt
from fastapi import (
    APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from shared.auth import JWTPayload, current_user
from shared.config import settings
from shared.db import get_db
from shared.models import CalendarEvent, EventAttachment, EventParticipant
from shared.utils.uploads import delete_file, resolve_path, save_upload

log = logging.getLogger(__name__)

router = APIRouter()

# ── Constants ──────────────────────────────────────────────────────────────
SUPER_ROLES = frozenset({"admin", "ceo", "assistant_ceo"})
VALID_EVENT_TYPES = frozenset({"personal", "shared", "public"})
VALID_RECURRENCE = frozenset({"none", "daily", "weekday", "weekly", "monthly"})
_MAX_OCCURRENCES = 500  # chặn vòng lặp expansion
DEFAULT_TZ = "Asia/Ho_Chi_Minh"


def _resolve_tz(tz_str: Optional[str]):
    """Trả tzinfo cho tz_str, fail-soft về Asia/Ho_Chi_Minh."""
    name = (tz_str or DEFAULT_TZ).strip() or DEFAULT_TZ
    try:
        try:
            from zoneinfo import ZoneInfo  # py>=3.9
            return ZoneInfo(name)
        except Exception:
            import pytz  # type: ignore
            return pytz.timezone(name)
    except Exception:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(DEFAULT_TZ)
        except Exception:
            return timezone.utc


def _ensure_aware(dt: datetime, tz_str: Optional[str] = None) -> datetime:
    """Bảo đảm datetime tz-aware. Naive → gán tz mặc định (Asia/Ho_Chi_Minh)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_resolve_tz(tz_str))
    return dt


def _is_super(user: JWTPayload) -> bool:
    return (user.role or "").lower() in SUPER_ROLES


# ── Schemas ────────────────────────────────────────────────────────────────

class ParticipantOut(BaseModel):
    username: str
    status: str
    role: str


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    start_dt: datetime
    end_dt: datetime
    all_day: bool = False
    event_type: str = Field(default="personal")
    location: Optional[str] = Field(default=None, max_length=255)
    color: Optional[str] = Field(default=None, max_length=16)
    timezone: Optional[str] = Field(default=DEFAULT_TZ, max_length=64)
    reminder_minutes: Optional[int] = Field(default=None, ge=0, le=60 * 24 * 30)
    recurrence: Optional[str] = Field(default=None, max_length=16)
    recurrence_until: Optional[datetime] = None
    participants: list[str] = Field(default_factory=list)

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, v: str) -> str:
        v2 = (v or "personal").lower().strip()
        if v2 not in VALID_EVENT_TYPES:
            raise ValueError(f"event_type phải là một trong {sorted(VALID_EVENT_TYPES)}")
        return v2

    @field_validator("recurrence")
    @classmethod
    def _validate_recurrence(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v2 = v.lower().strip()
        if not v2 or v2 == "none":
            return None
        if v2 not in VALID_RECURRENCE:
            raise ValueError(f"recurrence phải là một trong {sorted(VALID_RECURRENCE)}")
        return v2


class EventUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    start_dt: Optional[datetime] = None
    end_dt: Optional[datetime] = None
    all_day: Optional[bool] = None
    event_type: Optional[str] = None
    location: Optional[str] = Field(default=None, max_length=255)
    color: Optional[str] = Field(default=None, max_length=16)
    timezone: Optional[str] = Field(default=None, max_length=64)
    reminder_minutes: Optional[int] = Field(default=None, ge=0, le=60 * 24 * 30)
    recurrence: Optional[str] = Field(default=None, max_length=16)
    recurrence_until: Optional[datetime] = None

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v2 = v.lower().strip()
        if v2 not in VALID_EVENT_TYPES:
            raise ValueError(f"event_type phải là một trong {sorted(VALID_EVENT_TYPES)}")
        return v2

    @field_validator("recurrence")
    @classmethod
    def _validate_recurrence(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v2 = v.lower().strip()
        if not v2 or v2 == "none":
            return "none"  # cho phép tắt lặp khi update
        if v2 not in VALID_RECURRENCE:
            raise ValueError(f"recurrence phải là một trong {sorted(VALID_RECURRENCE)}")
        return v2


class AttachmentOut(BaseModel):
    id: int
    filename: str
    url: str
    size: int
    content_type: Optional[str] = None
    uploaded_by: str
    created_at: datetime


class EventOut(BaseModel):
    id: int
    owner_username: str
    title: str
    description: Optional[str] = None
    start_dt: datetime
    end_dt: datetime
    all_day: bool
    event_type: str
    location: Optional[str] = None
    color: Optional[str] = None
    timezone: str
    source: Optional[str] = None
    source_ref_id: Optional[str] = None
    reminder_minutes: Optional[int] = None
    recurrence: Optional[str] = None
    recurrence_until: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    my_status: Optional[str] = None
    participants: list[ParticipantOut] = Field(default_factory=list)
    attachments: list[AttachmentOut] = Field(default_factory=list)
    # Lặp lại: mỗi lần hiện = 1 occurrence. occ_id = id duy nhất cho FullCalendar;
    # master_id = id gốc để sửa/xoá cả chuỗi.
    occ_id: Optional[str] = None
    master_id: Optional[int] = None
    is_occurrence: bool = False


class InviteBody(BaseModel):
    usernames: list[str] = Field(default_factory=list)


class RespondBody(BaseModel):
    status: Literal["accepted", "declined"]


# ── Helpers ────────────────────────────────────────────────────────────────

def _participants_out(ev: CalendarEvent) -> list[ParticipantOut]:
    return [
        ParticipantOut(username=p.username, status=p.status, role=p.role)
        for p in (ev.participants or [])
    ]


def _attachments_out(ev: CalendarEvent) -> list[AttachmentOut]:
    return [
        AttachmentOut(
            id=a.id,
            filename=a.filename,
            url=f"/api/calendar/attachments/{a.id}",
            size=a.size or 0,
            content_type=a.content_type,
            uploaded_by=a.uploaded_by,
            created_at=a.created_at,
        )
        for a in (ev.attachments or [])
    ]


def _my_status(ev: CalendarEvent, username: str) -> Optional[str]:
    """Trả status của username trong event (owner → 'accepted')."""
    if ev.owner_username == username:
        # Nếu owner đã có participant row thì lấy status đó, không thì 'accepted'
        for p in ev.participants or []:
            if p.username == username:
                return p.status
        return "accepted"
    for p in ev.participants or []:
        if p.username == username:
            return p.status
    return None


def _to_out(
    ev: CalendarEvent,
    username: str,
    *,
    occ_start: Optional[datetime] = None,
    occ_end: Optional[datetime] = None,
) -> dict[str, Any]:
    """Serialize event. Nếu truyền occ_start/occ_end → đây là 1 lần lặp (occurrence):
    thời gian đổi theo occ, occ_id duy nhất, master_id giữ id gốc để sửa/xoá."""
    rec = (ev.recurrence or None)
    if rec == "none":
        rec = None
    is_occ = occ_start is not None
    s_dt = occ_start if is_occ else ev.start_dt
    e_dt = occ_end if is_occ else ev.end_dt
    if is_occ:
        occ_id = f"{ev.id}::{s_dt.date().isoformat()}"
    else:
        occ_id = str(ev.id)
    return EventOut(
        id=ev.id,
        owner_username=ev.owner_username,
        title=ev.title,
        description=ev.description,
        start_dt=s_dt,
        end_dt=e_dt,
        all_day=bool(ev.all_day),
        event_type=ev.event_type,
        location=ev.location,
        color=ev.color,
        timezone=ev.timezone or DEFAULT_TZ,
        source=ev.source,
        source_ref_id=ev.source_ref_id,
        reminder_minutes=ev.reminder_minutes,
        recurrence=rec,
        recurrence_until=ev.recurrence_until,
        created_at=ev.created_at,
        updated_at=ev.updated_at,
        my_status=_my_status(ev, username),
        participants=_participants_out(ev),
        attachments=_attachments_out(ev),
        occ_id=occ_id,
        master_id=ev.id,
        is_occurrence=is_occ,
    ).model_dump(mode="json")


def _add_months(dt: datetime, n: int) -> datetime:
    """Cộng n tháng, giữ đúng ngày (clamp cuối tháng, vd 31/1 → 28/2)."""
    import calendar as _cal
    month = dt.month - 1 + n
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, _cal.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _next_occurrence(dt: datetime, freq: str) -> datetime:
    """Mốc bắt đầu kế tiếp theo tần suất."""
    if freq == "daily":
        return dt + timedelta(days=1)
    if freq == "weekly":
        return dt + timedelta(days=7)
    if freq == "monthly":
        return _add_months(dt, 1)
    if freq == "weekday":
        nxt = dt + timedelta(days=1)
        while nxt.weekday() >= 5:  # 5=Sat, 6=Sun
            nxt += timedelta(days=1)
        return nxt
    return dt + timedelta(days=1)


def _expand_events(
    ev: CalendarEvent, username: str, range_start: datetime, range_end: datetime
) -> list[dict[str, Any]]:
    """Trả list _to_out cho event trong [range_start, range_end).
    Event thường → 1 phần tử. Event lặp → nhiều occurrence overlap window."""
    freq = (ev.recurrence or "none")
    if freq in ("none", "", None):
        return [_to_out(ev, username)]

    duration = ev.end_dt - ev.start_dt
    until = ev.recurrence_until
    out: list[dict[str, Any]] = []
    cur = ev.start_dt
    guard = 0
    while cur < range_end and guard < _MAX_OCCURRENCES:
        guard += 1
        if until is not None and cur > until:
            break
        occ_end = cur + duration
        if occ_end > range_start:  # overlap window
            out.append(_to_out(ev, username, occ_start=cur, occ_end=occ_end))
        cur = _next_occurrence(cur, freq)
    return out


def _can_view(ev: CalendarEvent, username: str) -> bool:
    if ev.owner_username == username:
        return True
    for p in ev.participants or []:
        if p.username == username:
            return True
    return False


def _notify_invited(db: Session, ev: CalendarEvent, target: str, by: str):
    """Notify NV khi được mời tham gia event. Fail-soft."""
    try:
        from shared.services.notify import notify
    except Exception:
        return
    try:
        start_str = ev.start_dt.strftime("%H:%M %d/%m/%Y") if ev.start_dt else ""
    except Exception:
        start_str = str(ev.start_dt) if ev.start_dt else ""
    try:
        notify(
            db, target=target, source_app="calendar",
            event_type="calendar:invited",
            title=f"[Lịch] {ev.title} — {start_str}",
            message=f"{by} mời bạn tham gia lịch '{ev.title}'"
                    + (f" tại {ev.location}" if ev.location else ""),
            ref_type="calendar_event", ref_id=ev.id,
            url=f"/lich-lam-viec#event={ev.id}",
            severity="info",
            created_by=by,
        )
    except Exception as e:
        log.debug("notify_invited skip: %s", e)


# ── 1. List events trong khoảng ────────────────────────────────────────────

@router.get("/events")
def list_events(
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    start: datetime = Query(..., description="ISO 8601 start (inclusive)"),
    end: datetime = Query(..., description="ISO 8601 end (exclusive)"),
    include_shared: bool = Query(True, description="Include events user được invite"),
) -> dict:
    """List events user là owner HOẶC participant (accepted/invited) overlap [start,end)."""
    start_aw = _ensure_aware(start)
    end_aw = _ensure_aware(end)
    if not (start_aw < end_aw):
        raise HTTPException(400, "start phải < end")

    _is_recurring = and_(
        CalendarEvent.recurrence.isnot(None),
        CalendarEvent.recurrence != "none",
    )
    # Event thường: overlap [start,end). Event lặp: bắt đầu trước end + chưa kết thúc lặp
    # trước start (occurrence có thể rơi vào window dù start_dt gốc ở quá khứ).
    time_cond = or_(
        and_(
            ~_is_recurring,
            CalendarEvent.start_dt < end_aw,
            CalendarEvent.end_dt > start_aw,
        ),
        and_(
            _is_recurring,
            CalendarEvent.start_dt < end_aw,
            or_(
                CalendarEvent.recurrence_until.is_(None),
                CalendarEvent.recurrence_until > start_aw,
            ),
        ),
    )
    if include_shared:
        # Owner OR participant (status invited/accepted)
        participant_subq = (
            select(EventParticipant.event_id).where(
                EventParticipant.username == user.username,
                EventParticipant.status.in_(("invited", "accepted")),
            )
        )
        cond = or_(
            CalendarEvent.owner_username == user.username,
            CalendarEvent.id.in_(participant_subq),
        )
    else:
        cond = CalendarEvent.owner_username == user.username

    stmt = (
        select(CalendarEvent)
        .where(and_(time_cond, cond))
        .options(selectinload(CalendarEvent.participants))
        .order_by(CalendarEvent.start_dt.asc())
    )
    rows = db.execute(stmt).scalars().all()
    items: list[dict[str, Any]] = []
    for ev in rows:
        items.extend(_expand_events(ev, user.username, start_aw, end_aw))
    return {"total": len(items), "items": items}


# ── 2. Create event ────────────────────────────────────────────────────────

@router.post("/events", status_code=status.HTTP_201_CREATED)
def create_event(
    body: EventCreate,
    request: Request,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    tz_str = (body.timezone or DEFAULT_TZ).strip() or DEFAULT_TZ
    start_aw = _ensure_aware(body.start_dt, tz_str)
    end_aw = _ensure_aware(body.end_dt, tz_str)
    if not (start_aw < end_aw):
        raise HTTPException(400, "start_dt phải < end_dt")

    ev = CalendarEvent(
        owner_username=user.username,
        title=body.title,
        description=body.description,
        start_dt=start_aw,
        end_dt=end_aw,
        all_day=bool(body.all_day),
        event_type=body.event_type or "personal",
        location=body.location,
        color=body.color,
        timezone=tz_str,
        source="manual",
        reminder_minutes=body.reminder_minutes,
        recurrence=body.recurrence,
        recurrence_until=(
            _ensure_aware(body.recurrence_until, tz_str) if body.recurrence_until else None
        ),
    )
    db.add(ev)
    db.flush()

    # Participants
    invited_users: list[str] = []
    seen: set[str] = set()
    raw_parts = [u for u in (body.participants or []) if u]
    if raw_parts:
        # Owner luôn là participant 'accepted' organizer
        owner_p = EventParticipant(
            event_id=ev.id, username=user.username,
            status="accepted", role="organizer",
        )
        db.add(owner_p)
        seen.add(user.username)
        for u in raw_parts:
            uname = (u or "").strip()
            if not uname or uname in seen:
                continue
            seen.add(uname)
            p = EventParticipant(
                event_id=ev.id, username=uname,
                status="invited", role="attendee",
            )
            db.add(p)
            invited_users.append(uname)
        db.flush()

    # Notify invitees (after flush để có ev.id)
    for u in invited_users:
        _notify_invited(db, ev, u, by=user.username)

    db.commit()
    db.refresh(ev)
    return {"ok": True, "id": ev.id, "item": _to_out(ev, user.username)}


# ── 3. Detail ──────────────────────────────────────────────────────────────

@router.get("/events/by-source/{source}/{ref_id}")
def get_event_by_source(
    source: str,
    ref_id: str,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Tìm event auto-created từ source (vd leave_request/123)."""
    stmt = (
        select(CalendarEvent)
        .where(
            CalendarEvent.source == source,
            CalendarEvent.source_ref_id == str(ref_id),
        )
        .options(selectinload(CalendarEvent.participants))
        .order_by(CalendarEvent.id.desc())
    )
    rows = db.execute(stmt).scalars().all()
    # Filter chỉ event user xem được
    items = [_to_out(ev, user.username) for ev in rows if _can_view(ev, user.username)]
    return {"total": len(items), "items": items}


@router.get("/events/{id}")
def get_event(
    id: int,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    ev = db.execute(
        select(CalendarEvent)
        .where(CalendarEvent.id == id)
        .options(selectinload(CalendarEvent.participants))
    ).scalar_one_or_none()
    if not ev:
        raise HTTPException(404, "Event không tồn tại")
    if not _can_view(ev, user.username):
        # Trả 404 thay vì 403 để khỏi leak existence
        raise HTTPException(404, "Event không tồn tại")
    return _to_out(ev, user.username)


# ── 4. Update (chỉ owner) ──────────────────────────────────────────────────

@router.put("/events/{id}")
def update_event(
    id: int,
    body: EventUpdate,
    request: Request,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    ev = db.execute(
        select(CalendarEvent)
        .where(CalendarEvent.id == id)
        .options(selectinload(CalendarEvent.participants))
    ).scalar_one_or_none()
    if not ev:
        raise HTTPException(404, "Event không tồn tại")
    if ev.owner_username != user.username:
        raise HTTPException(403, "Chỉ chủ event mới được sửa")

    data = body.model_dump(exclude_unset=True)
    tz_str = data.get("timezone") or ev.timezone or DEFAULT_TZ

    if "title" in data and data["title"] is not None:
        ev.title = data["title"]
    if "description" in data:
        ev.description = data["description"]
    if "all_day" in data and data["all_day"] is not None:
        ev.all_day = bool(data["all_day"])
    if "event_type" in data and data["event_type"] is not None:
        ev.event_type = data["event_type"]
    if "location" in data:
        ev.location = data["location"]
    if "color" in data:
        ev.color = data["color"]
    if "timezone" in data and data["timezone"]:
        ev.timezone = data["timezone"]
    if "reminder_minutes" in data:
        ev.reminder_minutes = data["reminder_minutes"]
    if "recurrence" in data:
        rec = data["recurrence"]
        ev.recurrence = None if (rec in (None, "none", "")) else rec
    if "recurrence_until" in data:
        ru = data["recurrence_until"]
        ev.recurrence_until = _ensure_aware(ru, tz_str) if ru else None

    new_start = _ensure_aware(data["start_dt"], tz_str) if data.get("start_dt") else ev.start_dt
    new_end = _ensure_aware(data["end_dt"], tz_str) if data.get("end_dt") else ev.end_dt
    if not (new_start < new_end):
        raise HTTPException(400, "start_dt phải < end_dt")
    ev.start_dt = new_start
    ev.end_dt = new_end

    db.commit()
    db.refresh(ev)
    return {"ok": True, "id": ev.id, "item": _to_out(ev, user.username)}


# ── 5. Delete (owner hoặc admin/ceo) ───────────────────────────────────────

@router.delete("/events/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    id: int,
    request: Request,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    ev = db.get(CalendarEvent, id)
    if not ev:
        raise HTTPException(404, "Event không tồn tại")
    if ev.owner_username != user.username and not _is_super(user):
        raise HTTPException(403, "Chỉ chủ event hoặc admin/CEO mới được xoá")
    db.delete(ev)
    db.commit()
    return None


# ── 6. Invite participants ─────────────────────────────────────────────────

@router.post("/events/{id}/invite")
def invite_participants(
    id: int,
    body: InviteBody,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    ev = db.execute(
        select(CalendarEvent)
        .where(CalendarEvent.id == id)
        .options(selectinload(CalendarEvent.participants))
    ).scalar_one_or_none()
    if not ev:
        raise HTTPException(404, "Event không tồn tại")
    if ev.owner_username != user.username:
        raise HTTPException(403, "Chỉ chủ event mới được mời thành viên")

    existing = {p.username for p in (ev.participants or [])}
    # Bảo đảm owner luôn có row organizer/accepted (nếu chưa có)
    if user.username not in existing:
        db.add(EventParticipant(
            event_id=ev.id, username=user.username,
            status="accepted", role="organizer",
        ))
        existing.add(user.username)

    added: list[str] = []
    for u in (body.usernames or []):
        uname = (u or "").strip()
        if not uname or uname in existing:
            continue
        existing.add(uname)
        db.add(EventParticipant(
            event_id=ev.id, username=uname,
            status="invited", role="attendee",
        ))
        added.append(uname)

    db.flush()
    for u in added:
        _notify_invited(db, ev, u, by=user.username)
    db.commit()
    db.refresh(ev)
    return {
        "ok": True, "id": ev.id, "added": added,
        "item": _to_out(ev, user.username),
    }


# ── 7. Respond invitation ──────────────────────────────────────────────────

@router.post("/events/{id}/respond")
def respond_invitation(
    id: int,
    body: RespondBody,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    ev = db.execute(
        select(CalendarEvent)
        .where(CalendarEvent.id == id)
        .options(selectinload(CalendarEvent.participants))
    ).scalar_one_or_none()
    if not ev:
        raise HTTPException(404, "Event không tồn tại")

    # Tìm participant row
    target: Optional[EventParticipant] = None
    for p in ev.participants or []:
        if p.username == user.username:
            target = p
            break
    if target is None:
        raise HTTPException(403, "Bạn chưa được mời tham gia event này")
    if target.role == "organizer":
        raise HTTPException(400, "Organizer không cần respond")

    target.status = body.status
    db.commit()
    db.refresh(ev)
    return {
        "ok": True, "id": ev.id, "status": target.status,
        "item": _to_out(ev, user.username),
    }


# ── 8. Conflicts ───────────────────────────────────────────────────────────

@router.get("/conflicts")
def list_conflicts(
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    start: datetime = Query(..., description="ISO 8601 start"),
    end: datetime = Query(..., description="ISO 8601 end"),
) -> dict:
    """List event của user (owner OR participant accepted) overlap [start,end)."""
    start_aw = _ensure_aware(start)
    end_aw = _ensure_aware(end)
    if not (start_aw < end_aw):
        raise HTTPException(400, "start phải < end")

    participant_subq = (
        select(EventParticipant.event_id).where(
            EventParticipant.username == user.username,
            EventParticipant.status == "accepted",
        )
    )
    stmt = (
        select(CalendarEvent)
        .where(
            CalendarEvent.start_dt < end_aw,
            CalendarEvent.end_dt > start_aw,
            or_(
                CalendarEvent.owner_username == user.username,
                CalendarEvent.id.in_(participant_subq),
            ),
        )
        .order_by(CalendarEvent.start_dt.asc())
    )
    rows = db.execute(stmt).scalars().all()
    items = [
        {
            "id": ev.id,
            "title": ev.title,
            "start_dt": ev.start_dt.isoformat() if ev.start_dt else None,
            "end_dt": ev.end_dt.isoformat() if ev.end_dt else None,
        }
        for ev in rows
    ]
    return {"total": len(items), "items": items}


# ── 9. iCal feed (subscribe .ics vào Google/Apple Calendar) ────────────────
#
# Calendar app trên điện thoại KHÔNG gửi cookie/Authorization khi poll feed,
# nên feed.ics tự xác thực bằng token KÝ trong query. Token ký bằng cùng
# pyjwt + JWT_SECRET_KEY (settings.jwt_secret_key/jwt_alg) như access token,
# phân biệt bằng claim purpose="calendar_feed" nên KHÔNG dùng lẫn được với
# access token (current_user chặn typ!=access; feed chặn purpose!=calendar_feed).

FEED_TOKEN_PURPOSE = "calendar_feed"
FEED_TOKEN_TTL_DAYS = 365
FEED_WINDOW_PAST_DAYS = 30
FEED_WINDOW_FUTURE_DAYS = 180


def _issue_feed_token(username: str) -> str:
    """Ký feed token dài hạn (365 ngày) bằng pyjwt + JWT_SECRET_KEY."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        "username": username,
        "purpose": FEED_TOKEN_PURPOSE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=FEED_TOKEN_TTL_DAYS)).timestamp()),
    }
    return _jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_alg)


def _verify_feed_token(token: str) -> str:
    """Verify chữ ký + hạn + purpose. Trả username. Sai → HTTPException 401."""
    try:
        raw = _jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_alg])
    except _jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token feed đã hết hạn")
    except _jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Token feed không hợp lệ: {e}")
    if raw.get("purpose") != FEED_TOKEN_PURPOSE:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token feed sai mục đích")
    username = raw.get("username")
    if not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token feed thiếu username")
    return str(username)


def _ics_escape(text: Optional[str]) -> str:
    """Escape text-value theo RFC5545: \\ ; , và xuống dòng → \\n."""
    if text is None:
        return ""
    s = str(text)
    s = s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    s = s.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    return s


def _ics_fold(line: str) -> str:
    """Fold dòng > 75 octet (RFC5545 §3.1), an toàn ký tự multibyte UTF-8."""
    if len(line.encode("utf-8")) <= 75:
        return line
    chunks: list[bytes] = []
    cur = b""
    for ch in line:
        b = ch.encode("utf-8")
        # dòng đầu ≤75 octet; dòng tiếp có prefix 1 space nên nội dung ≤74
        limit = 75 if not chunks else 74
        if len(cur) + len(b) > limit:
            chunks.append(cur)
            cur = b
        else:
            cur += b
    chunks.append(cur)
    return "\r\n ".join(c.decode("utf-8") for c in chunks)


def _fmt_utc(dt: datetime) -> str:
    """datetime tz-aware → 'YYYYMMDDTHHMMSSZ' (UTC)."""
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _build_vevent(ev: CalendarEvent, dtstamp: str) -> list[str]:
    """Dựng các dòng VEVENT cho 1 event. Raise nếu dữ liệu hỏng (caller bỏ qua)."""
    tz_str = ev.timezone or DEFAULT_TZ
    start = _ensure_aware(ev.start_dt, tz_str)
    end = _ensure_aware(ev.end_dt, tz_str) if ev.end_dt else start
    out = [
        "BEGIN:VEVENT",
        f"UID:{ev.id}@qlpps.com",
        f"DTSTAMP:{dtstamp}",
    ]
    if ev.all_day:
        # DATE-value: DTEND non-inclusive (giữ nguyên ngày lưu trong DB)
        out.append(f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}")
        out.append(f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}")
    else:
        out.append(f"DTSTART:{_fmt_utc(start)}")
        out.append(f"DTEND:{_fmt_utc(end)}")
    out.append(f"SUMMARY:{_ics_escape(ev.title)}")
    if ev.description:
        out.append(f"DESCRIPTION:{_ics_escape(ev.description)}")
    if ev.location:
        out.append(f"LOCATION:{_ics_escape(ev.location)}")
    # Lặp lại → RRULE (Google/Apple Calendar tự expand phía client)
    _freq_map = {"daily": "DAILY", "weekly": "WEEKLY", "monthly": "MONTHLY"}
    rec = (getattr(ev, "recurrence", None) or "none")
    if rec in _freq_map:
        rrule = f"FREQ={_freq_map[rec]}"
        if ev.recurrence_until:
            try:
                rrule += f";UNTIL={_fmt_utc(_ensure_aware(ev.recurrence_until))}"
            except Exception:
                pass
        out.append(f"RRULE:{rrule}")
    elif rec == "weekday":
        rrule = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
        if ev.recurrence_until:
            try:
                rrule += f";UNTIL={_fmt_utc(_ensure_aware(ev.recurrence_until))}"
            except Exception:
                pass
        out.append(f"RRULE:{rrule}")
    if getattr(ev, "updated_at", None):
        try:
            out.append(f"LAST-MODIFIED:{_fmt_utc(_ensure_aware(ev.updated_at))}")
        except Exception:
            pass
    out.append("END:VEVENT")
    return out


def _build_ics(events: list[CalendarEvent]) -> str:
    """Dựng 1 VCALENDAR hợp lệ. Event lỗi → bỏ qua, không sập cả feed."""
    dtstamp = _fmt_utc(datetime.now(tz=timezone.utc))
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//QLPPS//Lich Lam Viec//VI",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:QLPPS - Lich lam viec",
        "X-WR-TIMEZONE:Asia/Ho_Chi_Minh",
    ]
    for ev in events:
        try:
            lines.extend(_build_vevent(ev, dtstamp))
        except Exception as e:
            log.warning("feed.ics bỏ qua event %s: %s", getattr(ev, "id", "?"), e)
            continue
    lines.append("END:VCALENDAR")
    # RFC5545: dòng phân tách bằng CRLF, fold dòng dài
    return "\r\n".join(_ics_fold(ln) for ln in lines) + "\r\n"


@router.get("/feed-token")
def get_feed_token(
    request: Request,
    user: Annotated[JWTPayload, Depends(current_user)],
) -> dict:
    """Sinh URL + token để subscribe lịch vào Google/Apple Calendar.

    Dán URL vào: iPhone → Cài đặt → Lịch → Tài khoản → Thêm đăng ký lịch;
    Google Calendar (web) → Thêm lịch khác → Từ URL. Token hạn 365 ngày,
    ai có URL này xem được lịch của bạn nên đừng chia sẻ công khai.
    """
    token = _issue_feed_token(user.username)
    base = str(request.base_url)
    if base.startswith("http://"):  # ép https cho subscribe trên di động
        base = "https://" + base[len("http://"):]
    base = base.rstrip("/")
    url = f"{base}/api/calendar/feed.ics?token={token}"
    return {
        "url": url,
        "token": token,
        "huong_dan": (
            "iPhone: Cài đặt → Lịch → Tài khoản → Thêm tài khoản → "
            "Khác → Thêm lịch đã đăng ký, dán URL này. "
            "Google Calendar: Lịch khác → Từ URL. Token hạn 365 ngày, "
            "giữ URL bí mật vì ai có cũng xem được lịch của bạn."
        ),
    }


@router.get("/feed.ics")
def calendar_feed(
    db: Annotated[Session, Depends(get_db)],
    token: str = Query(..., description="Feed token ký (thay cookie auth)"),
) -> Response:
    """Trả file .ics cho calendar app subscribe (auth bằng token trong query)."""
    username = _verify_feed_token(token)

    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(days=FEED_WINDOW_PAST_DAYS)
    window_end = now + timedelta(days=FEED_WINDOW_FUTURE_DAYS)

    participant_subq = (
        select(EventParticipant.event_id).where(
            EventParticipant.username == username,
            EventParticipant.status == "accepted",
        )
    )
    stmt = (
        select(CalendarEvent)
        .where(
            CalendarEvent.start_dt < window_end,
            CalendarEvent.end_dt > window_start,
            or_(
                CalendarEvent.owner_username == username,
                CalendarEvent.id.in_(participant_subq),
            ),
        )
        .order_by(CalendarEvent.start_dt.asc())
    )
    rows = db.execute(stmt).scalars().all()

    body = _build_ics(list(rows))
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="qlpps-lich.ics"'},
    )


# ── 10. Attachments (tài liệu đính kèm event: CV phỏng vấn, tài liệu họp...) ─
# File lưu qua shared.utils.uploads: {UPLOAD_DIR}/calendar/event_{id}/<uuid>.<ext>
# (PDF/Word/Excel/ảnh, tối đa 20MB). Ai xem được event thì đính kèm + tải được.

CAL_UPLOAD_APP = "calendar"


def _att_scope(event_id: int) -> str:
    return f"event_{event_id}"


def _load_event_with_parts(db: Session, event_id: int) -> Optional[CalendarEvent]:
    return db.execute(
        select(CalendarEvent)
        .where(CalendarEvent.id == event_id)
        .options(selectinload(CalendarEvent.participants))
    ).scalar_one_or_none()


@router.post("/events/{id}/attachments", status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    id: int,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
) -> dict:
    """Đính kèm 1 tài liệu vào event. Ai xem được event (owner/participant) thì đính kèm được."""
    ev = _load_event_with_parts(db, id)
    if not ev or not _can_view(ev, user.username):
        raise HTTPException(404, "Event không tồn tại")

    scope = _att_scope(ev.id)
    stored_name, _url, size = await save_upload(
        file, CAL_UPLOAD_APP, scope, allow_docs=True,
    )
    att = EventAttachment(
        event_id=ev.id,
        filename=(file.filename or stored_name)[:255],
        stored_name=stored_name,
        scope=scope,
        size=size,
        content_type=(file.content_type or None),
        uploaded_by=user.username,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return {
        "ok": True,
        "attachment": AttachmentOut(
            id=att.id, filename=att.filename,
            url=f"/api/calendar/attachments/{att.id}",
            size=att.size or 0, content_type=att.content_type,
            uploaded_by=att.uploaded_by, created_at=att.created_at,
        ).model_dump(mode="json"),
    }


@router.get("/attachments/{aid}")
def download_attachment(
    aid: int,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Xem/tải tài liệu đính kèm. Chỉ người xem được event mới truy cập (chống lộ file)."""
    att = db.get(EventAttachment, aid)
    if not att:
        raise HTTPException(404, "Tài liệu không tồn tại")
    ev = _load_event_with_parts(db, att.event_id)
    if not ev or not _can_view(ev, user.username):
        raise HTTPException(404, "Tài liệu không tồn tại")
    path = resolve_path(CAL_UPLOAD_APP, att.scope, att.stored_name)
    if path is None:
        raise HTTPException(404, "File đã bị xoá khỏi máy chủ")
    return FileResponse(
        str(path),
        media_type=att.content_type or "application/octet-stream",
        filename=att.filename,
        content_disposition_type="inline",  # PDF/ảnh xem ngay trong trình duyệt
    )


@router.delete("/attachments/{aid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    aid: int,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Xoá tài liệu: người upload, chủ event, hoặc admin/CEO."""
    att = db.get(EventAttachment, aid)
    if not att:
        raise HTTPException(404, "Tài liệu không tồn tại")
    ev = db.get(CalendarEvent, att.event_id)
    owner = ev.owner_username if ev else None
    if att.uploaded_by != user.username and owner != user.username and not _is_super(user):
        raise HTTPException(403, "Không có quyền xoá tài liệu này")
    delete_file(CAL_UPLOAD_APP, att.scope, att.stored_name)  # best-effort xoá file vật lý
    db.delete(att)
    db.commit()
    return None
