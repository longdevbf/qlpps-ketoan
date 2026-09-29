"""Giao việc / Chỉ đạo — shared router mount mọi app.

Cùng table `shared.directives`. CEO tạo task → NV nhận thấy ở app của mình.

Status enum mới (v2 — migration 0032_directive_status_v2):
  assigned     — vừa giao, NV chưa start
  in_progress  — NV đã "Bắt đầu" / "Tiếp tục"
  blocked      — NV "Tạm dừng" (kèm blocked_reason)
  done         — NV "Hoàn thành"
  cancelled    — CEO/from_user huỷ (legacy 'dropped')

Endpoints (mount /api/giao-viec):
  GET  /recipients      → CEO/manager/leader: list NV để chọn (dropdown)
  GET  /list            → CEO/manager/leader: task đã giao (?pham_vi=toi_giao|phong_ban|tat_ca)
  POST /                → CEO/manager/leader tạo task → notify NV
  GET  /{id}            → Detail (super hoặc from_user/to_user)
  POST /{id}/ack        → NV "Đã nhận" (assigned → assigned + acknowledged_at)
  POST /{id}/start      → NV "Bắt đầu" (assigned → in_progress)
  POST /{id}/pause      → NV "Tạm dừng" (in_progress → blocked) {reason}
  POST /{id}/resume     → NV "Tiếp tục" (blocked → in_progress)
  POST /{id}/complete   → NV "Hoàn thành" (in_progress → done) {response}
  POST /{id}/reopen     → CEO/from_user/super: mở lại task done (→ in_progress) {reason}
  POST /{id}/close      → CEO/from_user huỷ (cancelled) — legacy 'done' vẫn được map
  POST /{id}/respond    → NV cập nhật progress (giữ legacy)
  GET  /inbox           → NV xem task mình nhận (status / tab filter)
  POST   /{id}/tep      → Tải tệp đính kèm lên task (from_user/to_user/super) — 12/09/2026
  GET    /{id}/tep/{ma} → Mở tệp inline (ai xem được task thì mở được)
  DELETE /{id}/tep?ma=  → Xoá tệp (from_user/super)

KHÔNG đụng `ceo/app/routers/giao_viec.py` cũ — file đó sẽ replace bằng shim.
"""
from __future__ import annotations

import os
import re
import shutil
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, false, func, or_, select, text as sql_text
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload, current_user
from shared.config import settings
from shared.db import get_db
from shared.models import Directive, User
from shared.services.employees import lookup_employee, bulk_lookup


router = APIRouter()

VALID_APPS = frozenset({"baogia", "marketing", "muahang", "hcns", "ketoan", "saleadmin", "congnghe"})
VALID_PRIORITIES = frozenset({"low", "med", "high"})
SUPER_ROLES = frozenset({"admin", "ceo", "assistant_ceo"})
# Hierarchy: ai có quyền giao việc (super bypass scope; manager/leader bị scope phòng)
ASSIGNER_ROLES = frozenset({"admin", "ceo", "assistant_ceo", "manager", "leader"})
# Cấp dưới hợp lệ theo role người giao
_SUBORDINATES = {
    "manager":   {"leader", "nhan_vien", "nv", "kd", "mkt", "mh"},
    "leader":    {"nhan_vien", "nv", "kd", "mkt", "mh"},
}

# ── Status constants (v2) ──────────────────────────────────────────────────
STATUS_ASSIGNED = "assigned"
STATUS_IN_PROGRESS = "in_progress"
STATUS_BLOCKED = "blocked"
STATUS_DONE = "done"
STATUS_CANCELLED = "cancelled"
ALL_STATUS = [STATUS_ASSIGNED, STATUS_IN_PROGRESS, STATUS_BLOCKED, STATUS_DONE, STATUS_CANCELLED]
_VALID_STATUS_SET = frozenset(ALL_STATUS)

# Tab → status set (dùng cho inbox/list)
_TAB_TO_STATUSES = {
    "waiting":  (STATUS_ASSIGNED, STATUS_BLOCKED),
    "working":  (STATUS_IN_PROGRESS,),
    "finished": (STATUS_DONE, STATUS_CANCELLED),
}

# Backward-compat cho status filter cũ
_LEGACY_STATUS_MAP = {
    "open":    (STATUS_ASSIGNED, STATUS_IN_PROGRESS, STATUS_BLOCKED),
    "dropped": (STATUS_CANCELLED,),
}

# Endpoint /close (legacy semantic) — chấp nhận 4 giá trị, map về v2
VALID_CLOSE_INPUT = frozenset({"done", "dropped", "cancelled", STATUS_CANCELLED})

# /list?pham_vi= (12/09/2026). Không truyền → giữ nguyên hành vi cũ (super thấy hết, còn lại chỉ
# thấy việc mình giao) để các màn đang gọi /list không đổi kết quả.
_PHAM_VI = frozenset({"toi_giao", "phong_ban", "tat_ca"})

# ── Tệp đính kèm (12/09/2026) ──────────────────────────────────────────────
# KHÔNG thêm cột DB (người dùng chốt 12/09/2026): tệp của task #N nằm ở `<upload_dir>/giao_viec/N/`,
# danh sách tệp = danh sách file trong thư mục đó. Tên trên đĩa `<12 hex>__<tên gốc đã lọc>` giữ
# được tên gốc để hiện mà không cần bảng phụ — cùng cách với `xin_nghi.py`. Thư mục uploads gắn
# chung mọi container nên tải lên ở app nào thì app khác vẫn mở được.
_TEP_SUBDIR = "giao_viec"
# Khai media type tường minh thay vì để FileResponse đoán theo đuôi: mimetypes trong image Python
# của hệ không biết .docx/.xlsx (guess_type trả None, đã thử trong container 12/09/2026).
# Key của dict này cũng là danh sách đuôi được nhận.
_TEP_MIME = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}
_TEP_MAX = 10 * 1024 * 1024   # 10 MB mỗi tệp
_TEP_TOI_DA = 10              # số tệp tối đa mỗi task
_TEP_MA_RE = re.compile(r"^[a-f0-9]{12}__[^/\\]{1,120}$")


# ── Schemas ────────────────────────────────────────────────────────────────

class CreateBody(BaseModel):
    # Backward-compat: hỗ trợ cả single (to_user) và multi (to_users).
    # Validate ở handler: phải có ít nhất 1 username từ một trong hai field.
    to_user: Optional[str] = Field(default=None, max_length=64)
    to_users: Optional[list[str]] = Field(default=None)
    app: str = Field(pattern=r"^(baogia|marketing|muahang|hcns|ketoan|saleadmin|congnghe)$")
    title: str = Field(min_length=1, max_length=255)
    body: Optional[str] = None
    priority: str = Field(default="med", pattern=r"^(low|med|high)$")
    due_date: Optional[date] = None


class CloseBody(BaseModel):
    # 'done' = legacy (cho phép nhưng deprecate),
    # 'dropped' / 'cancelled' = huỷ (map về 'cancelled')
    status: str = Field(pattern=r"^(done|dropped|cancelled)$")
    note: Optional[str] = None


class RespondBody(BaseModel):
    response: str = Field(min_length=1)


class PauseBody(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class CompleteBody(BaseModel):
    response: str = Field(min_length=1)


class ReopenBody(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class TepOut(BaseModel):
    ma: str          # tên trên đĩa — dùng để mở / xoá
    ten: str         # tên gốc để hiện
    url: str
    kich_thuoc: int  # byte


# ── Helpers ────────────────────────────────────────────────────────────────

def _is_super(user: JWTPayload) -> bool:
    return (user.role or "").lower() in SUPER_ROLES


def _can_assign(user: JWTPayload) -> bool:
    """User có role được phép tạo task (chưa check scope)."""
    return (user.role or "").lower() in ASSIGNER_ROLES


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _days_silent(d: Directive) -> Optional[int]:
    ts = d.last_activity_at or d.created_at
    if not ts:
        return None
    try:
        # Normalize tz-aware
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = _now_utc() - ts
        days = delta.days
        return days if days >= 0 else 0
    except Exception:
        return None


# Alias map các "phòng anh chị em" coi cùng 1 scope cho giao việc.
# Lý do: hiện DB tách 'Marketing', 'Quảng Cáo Ads', 'Media / Desginer', 'Tư Vấn - Lễ Tân'
# thành 4 phòng riêng dù về business chúng đều thuộc team Marketing. Không thể đổi DB
# vì còn cấp lương/báo cáo riêng — nên map ở app layer.
# Key = phòng "trùm" (lowercase, đã trim). Value = set phòng con coi cùng scope.
_DEPT_SCOPE_ALIASES = {
    "marketing": {
        "marketing",
        "quảng cáo ads",
        "media / desginer", "media / designer", "media/designer", "media",
        "tư vấn - lễ tân", "tu van - le tan",
    },
}


def _dept_in_scope(sender_pb: str, recipient_pb: str) -> bool:
    """Recipient nằm trong scope phòng của sender.

    Match rules:
    1. Exact: 'Marketing' == 'Marketing'
    2. Prefix: sender 'Kinh Doanh' → match recipient 'Kinh Doanh Bán Lẻ Nhóm 1'
    3. Alias: sender 'Marketing' → match recipient 'Quảng Cáo Ads' (cùng team Marketing)
    Empty/None không match (tránh quét toàn bộ).
    """
    if not sender_pb or not recipient_pb:
        return False
    s = sender_pb.strip().lower()
    r = recipient_pb.strip().lower()
    if r == s or r.startswith(s + " ") or r.startswith(s + "_") or r.startswith(s + "-"):
        return True
    # Alias match: nếu sender thuộc 1 "phòng trùm", check recipient nằm trong set alias
    aliases = _DEPT_SCOPE_ALIASES.get(s)
    if aliases and r in aliases:
        return True
    return False


def _user_phong_ban(username: str) -> Optional[str]:
    """Lấy phong_ban từ hcns.employees (qua cache _lookup_user_info)."""
    if not username:
        return None
    try:
        from shared.templates import _lookup_user_info
        _, pb, _, _, _ = _lookup_user_info(username)
        return pb or None
    except Exception:
        return None


def _validate_assign_scope(db: Session, sender: JWTPayload, recipient_username: str) -> Optional[str]:
    """Trả None nếu OK; trả string error nếu sender không có quyền giao cho recipient.

    Rule:
    - super (admin/ceo/assistant_ceo): giao mọi NV, mọi phòng
    - manager: chỉ giao cho leader/NV CÙNG phòng_ban
    - leader: chỉ giao cho NV CÙNG phòng_ban
    """
    role = (sender.role or "").lower()
    if role in SUPER_ROLES:
        return None
    if role not in ASSIGNER_ROLES:
        return "Bạn không có quyền tạo task"
    # Lookup recipient role + phong_ban
    info = lookup_employee(db, recipient_username) or {}
    recipient_role = (info.get("role") or "").lower()
    recipient_pb = info.get("phong_ban") or ""
    # Fallback: nếu không có info HCNS, đọc shared.users.role
    if not recipient_role:
        row = db.execute(
            select(User.role).where(User.username == recipient_username)
        ).scalar_one_or_none()
        recipient_role = (row or "").lower()
    allowed_subs = _SUBORDINATES.get(role, set())
    if recipient_role not in allowed_subs:
        return f"Bạn (role={role}) không thể giao cho người role={recipient_role or '?'}"
    sender_pb = _user_phong_ban(sender.username)
    if not sender_pb:
        return "Không xác định được phòng ban của bạn"
    if not _dept_in_scope(sender_pb, recipient_pb):
        return f"Bạn chỉ được giao cho NV trong phạm vi phòng '{sender_pb}' (NV này thuộc '{recipient_pb or '?'}')"
    return None


def _bulk_names(db: Session, usernames) -> dict[str, str]:
    unames = [u for u in (usernames or []) if u]
    if not unames:
        return {}
    infos = bulk_lookup(db, unames) or {}
    return {u: (infos.get(u, {}).get("ho_ten") or u) for u in unames}


def _bulk_names_pb(db: Session, usernames) -> tuple[dict[str, str], dict[str, Optional[str]]]:
    """Như `_bulk_names` + {username: phong_ban} lấy từ CÙNG một lần bulk_lookup (không tốn thêm
    truy vấn). Hàm riêng thay vì đổi `_bulk_names` để các endpoint đang gọi nó giữ nguyên."""
    unames = [u for u in (usernames or []) if u]
    if not unames:
        return {}, {}
    infos = bulk_lookup(db, unames) or {}
    names = {u: (infos.get(u, {}).get("ho_ten") or u) for u in unames}
    pbs = {u: ((infos.get(u, {}).get("phong_ban") or "").strip() or None) for u in unames}
    return names, pbs


def _usernames_cung_phong(db: Session, username: str) -> set[str]:
    """Username (chữ thường) của mọi hồ sơ HCNS cùng phạm vi phòng với `username`.

    Khớp phòng bằng `_dept_in_scope` — cùng luật lúc giao việc (trùng tên, tiền tố sub-team, alias
    team Marketing). Phòng của chính mình lấy trong CÙNG truy vấn thay vì gọi `_user_phong_ban`:
    helper đó nuốt lỗi DB thành None, trông y hệt "không có phòng ban" và làm danh sách rỗng im
    lặng. Không xác định được phòng → set rỗng.
    """
    rows = db.execute(sql_text("""
        SELECT LOWER(username) AS u, phong_ban
        FROM hcns.employees
        WHERE username IS NOT NULL AND username <> ''
    """)).all()
    me = (username or "").lower()
    my_pb = next(((r.phong_ban or "").strip() for r in rows if r.u == me), "")
    if not my_pb:
        return set()
    return {r.u for r in rows if _dept_in_scope(my_pb, r.phong_ban or "")}


def _dieu_kien_phong(unames: set[str]):
    """Task có người nhận HOẶC người giao nằm trong tập username (so chữ thường)."""
    ds = sorted(unames)
    return or_(func.lower(Directive.to_user).in_(ds), func.lower(Directive.from_user).in_(ds))


def _tep_goc() -> Path:
    return Path(settings.upload_dir).expanduser().resolve() / _TEP_SUBDIR


def _tep_dir(did: int) -> Path:
    return _tep_goc() / str(int(did))


def _tep_item(did: int, ma: str, kich_thuoc: int) -> dict[str, Any]:
    return {"ma": ma, "ten": ma.split("__", 1)[1],
            "url": f"/api/giao-viec/{int(did)}/tep/{quote(ma)}", "kich_thuoc": kich_thuoc}


def _ds_tep(did: int) -> list[dict[str, Any]]:
    """Tệp của một task, cũ trước mới sau. Thư mục chưa có → [] (không listdir)."""
    d = _tep_dir(did)
    if not d.is_dir():
        return []
    tep = []
    with os.scandir(d) as it:
        for e in it:
            if e.is_file() and _TEP_MA_RE.match(e.name):
                st = e.stat()
                tep.append((st.st_mtime, e.name, st.st_size))
    tep.sort()
    return [_tep_item(did, ten, size) for _, ten, size in tep]


def _ds_tep_nhieu(ids) -> dict[int, list[dict[str, Any]]]:
    """Tệp cho cả danh sách task: đọc thư mục `giao_viec/` MỘT lần để biết task nào có thư mục,
    rồi chỉ đọc thư mục của các task đó — tránh mỗi task trong list (limit tới 2000) một lần stat."""
    goc = _tep_goc()
    if not goc.is_dir():
        return {}
    with os.scandir(goc) as it:
        co_thu_muc = {e.name for e in it if e.is_dir()}
    return {i: _ds_tep(i) for i in ids if str(i) in co_thu_muc}


def _ten_goc_an_toan(filename: Optional[str], ext: str) -> str:
    """Tên gốc để hiện lại: bỏ thư mục, ký tự lạ; giữ chữ có dấu. Rỗng → 'tep'."""
    stem = Path((filename or "").replace("\\", "/")).stem
    stem = re.sub(r"[^\w\-. ()]+", "_", stem).strip(" ._") or "tep"
    return stem[:80] + ext


def _to_dict(
    d: Directive,
    name_map: dict[str, str],
    pb_map: Optional[dict[str, Optional[str]]] = None,
    tep_map: Optional[dict[int, list[dict[str, Any]]]] = None,
) -> dict[str, Any]:
    out = {
        "id": d.id,
        "group_id": d.group_id,
        "from_user": d.from_user,
        "from_user_name": name_map.get(d.from_user, d.from_user),
        "from_user_id": d.from_user_id,
        "to_user": d.to_user,
        "to_user_name": name_map.get(d.to_user, d.to_user),
        "to_user_id": d.to_user_id,
        "app": d.app,
        "title": d.title,
        "body": d.body,
        "status": d.status,
        "priority": d.priority,
        "due_date": d.due_date.isoformat() if d.due_date else None,
        "response": d.response,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "closed_at": d.closed_at.isoformat() if d.closed_at else None,
        # v2 tracking
        "acknowledged_at": d.acknowledged_at.isoformat() if d.acknowledged_at else None,
        "started_at": d.started_at.isoformat() if d.started_at else None,
        "blocked_at": d.blocked_at.isoformat() if d.blocked_at else None,
        "blocked_reason": d.blocked_reason,
        "last_activity_at": d.last_activity_at.isoformat() if d.last_activity_at else None,
        "completed_at": d.completed_at.isoformat() if d.completed_at else None,
        "days_silent": _days_silent(d),
        # 12/09/2026 — không phải cột DB, đọc từ thư mục tệp. Danh sách truyền `tep_map` dựng sẵn
        # (`_ds_tep_nhieu`); endpoint một task thì tự đọc thư mục của task đó.
        "tep_dinh_kem": tep_map.get(d.id, []) if tep_map is not None else _ds_tep(d.id),
    }
    # Chỉ gắn khi endpoint đã tra sẵn phòng ban (/list, /{id}). Endpoint khác không tra — trả null
    # ở đó sẽ bị hiểu nhầm là "người nhận không có phòng ban".
    if pb_map is not None:
        out["to_user_phong_ban"] = pb_map.get(d.to_user)
    return out


def _resolve_recipient_id(db: Session, username: str) -> Optional[int]:
    if not username:
        return None
    u = db.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()
    return u.id if u else None


def _recipient_exists(db: Session, username: str) -> bool:
    if not username:
        return False
    if db.execute(select(User.id).where(User.username == username)).scalar_one_or_none():
        return True
    return bool(lookup_employee(db, username))


def _notify_assignee(db: Session, d: Directive, *, by: str):
    """Notify NV khi nhận task (in-app SSE + web push)."""
    try:
        from shared.services.notify import notify
    except Exception:
        return
    url = f"/giao-viec#id={d.id}"
    prio_label = {"low": "Thấp", "med": "Vừa", "high": "Cao"}.get(d.priority, d.priority)
    due_txt = f" • Hạn: {d.due_date.isoformat()}" if d.due_date else ""
    notify(
        db, target=d.to_user, source_app=d.app or "ceo",
        event_type="directive:assigned",
        title=f"[Giao Việc #{d.id}] {d.title}",
        message=f"Ưu tiên: {prio_label}{due_txt}",
        ref_type="directive", ref_id=d.id, url=url, severity="info",
        created_by=by,
    )


def _notify_closed(db: Session, d: Directive, *, by: str, note: str = ""):
    try:
        from shared.services.notify import notify
    except Exception:
        return
    url = f"/giao-viec#id={d.id}"
    if d.status == STATUS_DONE:
        label, sev = "hoàn thành", "success"
    elif d.status == STATUS_CANCELLED:
        label, sev = "huỷ", "warning"
    else:
        label, sev = d.status, "info"
    notify(
        db, target=d.to_user, source_app=d.app or "ceo",
        event_type=f"directive:{d.status}",
        title=f"[Giao Việc #{d.id}] CEO đã đánh dấu {label}",
        message=note or "",
        ref_type="directive", ref_id=d.id, url=url, severity=sev,
        created_by=by,
    )


def _ten_cua(db: Session, username: str) -> str:
    """Tên hiển thị của người thao tác để ghép vào câu thông báo (18/09/2026).

    Trước đây message ghi thẳng `user.username` ("nv26025 đã hoàn thành") nên CEO
    không biết ai. `created_by`/`by` vẫn giữ username — đó là khoá, không đổi.
    """
    from shared.services.employees import ten_nv  # lazy: cùng kiểu import notify ở dưới
    return ten_nv(db, [username]).get(username, username)


def _notify_status_change(db: Session, d: Directive, *, by: str, event: str, message: str, severity: str = "info"):
    """Notify from_user (CEO/manager) khi NV thay đổi trạng thái task."""
    try:
        from shared.services.notify import notify
    except Exception:
        return
    url = f"/giao-viec#id={d.id}"
    notify(
        db, target=d.from_user, source_app=d.app or "ceo",
        event_type=f"directive:{event}",
        title=f"[Giao Việc #{d.id}] {d.title}",
        message=message,
        ref_type="directive", ref_id=d.id, url=url, severity=severity,
        created_by=by,
    )


def _append_response(existing: Optional[str], prefix: str, body_text: str) -> str:
    body_text = (body_text or "").strip()
    if not body_text:
        return (existing or "").strip()
    if (existing or "").strip():
        return (existing + "\n" + prefix + body_text).strip()
    return (prefix + body_text).strip()


def _normalize_status_filter(raw: Optional[str]) -> Optional[tuple[str, ...]]:
    """Convert filter string → tuple of valid statuses, hoặc None nếu 'all'.

    Hỗ trợ:
      - 'all' / '' / None → None (không filter)
      - 1 status v2 → tuple 1 phần tử
      - legacy 'open' → (assigned, in_progress, blocked)
      - legacy 'dropped' → (cancelled,)
      - CSV nhiều status → tuple
    Raise HTTPException 400 nếu giá trị lạ.
    """
    if raw is None:
        return None
    s = raw.strip().lower()
    if not s or s == "all":
        return None
    if s in _LEGACY_STATUS_MAP:
        return _LEGACY_STATUS_MAP[s]
    if "," in s:
        parts = [p.strip() for p in s.split(",") if p.strip()]
        out: list[str] = []
        for p in parts:
            if p in _LEGACY_STATUS_MAP:
                out.extend(_LEGACY_STATUS_MAP[p])
            elif p in _VALID_STATUS_SET:
                out.append(p)
            else:
                raise HTTPException(400, f"status '{p}' không hợp lệ")
        # de-dup giữ thứ tự
        seen = set(); res = []
        for x in out:
            if x not in seen:
                seen.add(x); res.append(x)
        return tuple(res) if res else None
    if s in _VALID_STATUS_SET:
        return (s,)
    raise HTTPException(400, f"status '{raw}' không hợp lệ")


def _resolve_tab(tab: Optional[str]) -> Optional[tuple[str, ...]]:
    if not tab:
        return None
    t = tab.strip().lower()
    if t not in _TAB_TO_STATUSES:
        raise HTTPException(400, "tab phải thuộc {waiting, working, finished}")
    return _TAB_TO_STATUSES[t]


def _ensure_recipient(d: Directive, user: JWTPayload):
    """403 nếu user không phải người nhận và không phải super."""
    if d.to_user != user.username and not _is_super(user):
        raise HTTPException(403, "Chỉ người nhận task mới thao tác được")


# ── 0. Recipients dropdown ──────────────────────────────────────────────────

@router.get("/recipients")
def list_recipients(
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    q: Optional[str] = Query(None, description="filter ho_ten/username"),
    phong_ban: Optional[str] = None,
) -> dict:
    """List NV có thể nhận giao việc.

    - super (admin/ceo/assistant_ceo): xem all
    - manager: xem leader/NV cùng phòng
    - leader: xem NV cùng phòng
    """
    if not _can_assign(user):
        raise HTTPException(403, "Bạn không có quyền tạo task")
    role = (user.role or "").lower()
    rows = db.execute(sql_text("""
        SELECT e.username, e.ho_ten, e.phong_ban, e.chuc_vu, e.role
        FROM hcns.employees e
        WHERE e.username IS NOT NULL AND e.username != ''
          AND e.trang_thai = 'Đang làm'
        UNION
        SELECT u.username, COALESCE(u.full_name, u.username) AS ho_ten,
               NULL::text, NULL::text, u.role
        FROM shared.users u
        WHERE u.active = TRUE
          AND u.username NOT IN (
              SELECT username FROM hcns.employees
              WHERE username IS NOT NULL AND trang_thai = 'Đang làm'
          )
        ORDER BY phong_ban NULLS LAST, ho_ten
    """)).all()
    # Sender scope cho manager/leader: filter cùng phòng + subordinate role
    sender_pb = _user_phong_ban(user.username) if role not in SUPER_ROLES else None
    allowed_subs = _SUBORDINATES.get(role, set())
    items = []
    needle = (q or "").strip().lower()
    for r in rows:
        uname = r[0]; ho_ten = r[1] or uname
        pb = r[2]; cv = r[3]; rrole = (r[4] or "").lower()
        # Bỏ chính mình khỏi dropdown
        if uname == user.username:
            continue
        # Scope filter manager/leader
        if role not in SUPER_ROLES:
            if not _dept_in_scope(sender_pb or "", pb or ""):
                continue
            if rrole not in allowed_subs:
                continue
        if phong_ban and (pb or "") != phong_ban:
            continue
        if needle and needle not in (uname or "").lower() and needle not in (ho_ten or "").lower():
            continue
        items.append({
            "username": uname, "ho_ten": ho_ten,
            "phong_ban": pb or "", "chuc_vu": cv or "", "role": rrole,
        })
    # 12/09/2026: gắn ma_nv bằng MỘT truy vấn riêng sau khi đã lọc, không thêm cột vào câu UNION
    # ở trên — UNION khử trùng lặp theo CẢ dòng, thêm cột là đổi điều kiện khử của câu đang chạy.
    # Một username có nhiều hồ sơ → ưu tiên hồ sơ 'Đang làm'. Chỉ có ở shared.users → ma_nv = "".
    if items:
        ma_rows = db.execute(
            sql_text("""
                SELECT DISTINCT ON (LOWER(username)) LOWER(username) AS u, ma_nv
                FROM hcns.employees
                WHERE LOWER(username) IN :unames
                ORDER BY LOWER(username), (trang_thai = 'Đang làm') DESC NULLS LAST, ma_nv
            """).bindparams(bindparam("unames", expanding=True)),
            {"unames": sorted({(it["username"] or "").lower() for it in items})},
        ).all()
        ma_map = {r.u: r.ma_nv for r in ma_rows}
        for it in items:
            it["ma_nv"] = ma_map.get((it["username"] or "").lower()) or ""
    return {"items": items, "total": len(items)}


# ── 1. List (CEO) ──────────────────────────────────────────────────────────

@router.get("/list")
def list_directives(
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    status_filter: Optional[str] = Query(None, alias="status"),
    tab: Optional[str] = Query(None, description="waiting|working|finished"),
    app: Optional[str] = None,
    to_user: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
    pham_vi: Optional[str] = Query(None, description="toi_giao|phong_ban|tat_ca — bỏ trống = hành vi cũ"),
) -> dict:
    """List task đã giao.

    Không truyền `pham_vi` (hành vi cũ):
    - super: xem all
    - manager/leader: chỉ xem task chính mình giao (from_user == username)
    - NV thường: 403

    `pham_vi` (12/09/2026 — vẫn chỉ role được giao việc mới gọi được):
    - toi_giao:  from_user == mình (mọi role được giao việc)
    - phong_ban: CHỈ super. Người nhận HOẶC người giao cùng phạm vi phòng với mình
                 (`_dept_in_scope`); không xác định được phòng của mình → rỗng
    - tat_ca:    CHỈ super → tất cả

    Siết lại 12/09/2026 theo yêu cầu người dùng: "nhân viên không thấy việc của nhân
    viên, chỉ CEO mới thấy việc của các nhân viên". Manager/leader gọi `phong_ban` hay
    `tat_ca` nhận 403 — họ chỉ còn phạm vi việc do chính mình giao. Đo trước khi siết:
    manager phòng Kinh Doanh thấy 46 việc, trong đó 36 việc của người ngoài phòng (do
    `_dept_in_scope` khớp theo tiền tố nên "Kinh Doanh" nuốt "Kinh Doanh Bán Lẻ Nhóm 1").
    """
    if not _can_assign(user):
        raise HTTPException(403, "Chỉ người có quyền giao task xem được list")
    q = db.query(Directive)
    pv = (pham_vi or "").strip().lower()
    if not pv:
        if not _is_super(user):
            # Manager/leader chỉ thấy task của chính họ
            q = q.filter(Directive.from_user == user.username)
    elif pv not in _PHAM_VI:
        raise HTTPException(400, "pham_vi phải thuộc {toi_giao, phong_ban, tat_ca}")
    elif pv == "toi_giao":
        q = q.filter(Directive.from_user == user.username)
    elif not _is_super(user):
        # phong_ban / tat_ca chỉ dành cho CEO/Admin. Manager/leader vẫn giao việc được
        # nhưng chỉ xem việc do chính mình giao (giao diện đã ẩn 2 nút này với họ).
        raise HTTPException(403, "Chỉ CEO/Admin xem được phạm vi này")
    elif pv == "phong_ban":
        cung_phong = _usernames_cung_phong(db, user.username)
        # false() thay vì return sớm: vẫn đi qua bước kiểm status/tab/app bên dưới, nên tham số
        # sai vẫn nhận 400 như người có phòng ban.
        q = q.filter(_dieu_kien_phong(cung_phong) if cung_phong else false())
    # tat_ca của super: không lọc

    # tab ưu tiên hơn status_filter nếu cả 2 cùng có
    tab_statuses = _resolve_tab(tab)
    if tab_statuses is not None:
        q = q.filter(Directive.status.in_(tab_statuses))
    else:
        statuses = _normalize_status_filter(status_filter)
        if statuses is not None:
            q = q.filter(Directive.status.in_(statuses))

    if app:
        if app not in VALID_APPS:
            raise HTTPException(400, "app không hợp lệ")
        q = q.filter(Directive.app == app)
    if to_user:
        q = q.filter(Directive.to_user == to_user)
    rows = q.order_by(Directive.created_at.desc()).limit(limit).all()
    unames = list({r.from_user for r in rows} | {r.to_user for r in rows})
    name_map, pb_map = _bulk_names_pb(db, unames)
    tep_map = _ds_tep_nhieu([r.id for r in rows])
    return {"total": len(rows), "items": [_to_dict(r, name_map, pb_map, tep_map) for r in rows]}


# ── 2. Create ──────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
def create_directive(
    body: CreateBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    if not _can_assign(user):
        raise HTTPException(403, "Bạn không có quyền tạo task (cần admin/ceo/manager/leader)")

    # Gom recipients từ to_user (single, legacy) + to_users (multi). De-dup, bỏ self.
    raw: list[str] = []
    if body.to_users:
        raw.extend(body.to_users)
    if body.to_user:
        raw.append(body.to_user)
    recipients: list[str] = []
    seen: set[str] = set()
    for u in raw:
        uname = (u or "").strip()
        if not uname or uname in seen:
            continue
        seen.add(uname)
        recipients.append(uname)
    if not recipients:
        raise HTTPException(400, "Chưa chọn NV nhận task")
    if user.username in seen:
        raise HTTPException(400, "Không thể tự giao task cho mình")

    # Validate tồn tại + scope cho TỪNG người trước khi tạo bất kỳ row nào.
    for uname in recipients:
        if not _recipient_exists(db, uname):
            raise HTTPException(400, f"Username '{uname}' không tồn tại")
        scope_err = _validate_assign_scope(db, user, uname)
        if scope_err:
            raise HTTPException(403, scope_err)

    # Tạo 1 row Directive cho mỗi recipient. Gắn cùng group_id nếu batch >1 người
    # để UI gom thành 1 thẻ. Batch 1 người → group_id = None (legacy).
    batch_group_id = uuid.uuid4().hex[:16] if len(recipients) > 1 else None
    now = _now_utc()
    created: list[Directive] = []
    for uname in recipients:
        d = Directive(
            from_user=user.username,
            from_user_id=user.sub,
            to_user=uname,
            to_user_id=_resolve_recipient_id(db, uname),
            app=body.app,
            title=body.title,
            body=body.body,
            priority=body.priority,
            due_date=body.due_date,
            status=STATUS_ASSIGNED,
            group_id=batch_group_id,
            last_activity_at=now,
        )
        db.add(d)
        created.append(d)
    db.flush()
    for d in created:
        _notify_assignee(db, d, by=user.username)
    db.commit()
    for d in created:
        db.refresh(d)

    # Auto-sync CalendarEvent cho từng directive nếu có due_date (fail-soft per row).
    if body.due_date:
        try:
            from shared.services.calendar_sync import upsert_event_from_directive
            for d in created:
                try:
                    upsert_event_from_directive(db, d)
                except Exception:
                    pass
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

    log_action(
        db, app=body.app, action="create_directive", user=user, request=request,
        resource=",".join(f"directive:{d.id}" for d in created),
        payload={
            "to_users": recipients,
            "count": len(created),
            "title": body.title,
            "priority": body.priority,
        },
    )
    try:
        from shared.services.activity_logger import log_activity
        for d in created:
            log_activity(db, user.username, action="directive_create", app=body.app,
                         ref_type="directive", ref_id=d.id,
                         metadata={"to_user": d.to_user, "priority": body.priority,
                                   "title": (body.title or "")[:100]})
    except Exception:
        pass

    unames = [user.username] + recipients
    name_map = _bulk_names(db, unames)
    items = [_to_dict(d, name_map) for d in created]
    return {
        "ok": True,
        "ids": [d.id for d in created],
        "count": len(created),
        "items": items,
        # Backward-compat: client cũ đọc `id` + `item` (lấy row đầu)
        "id": created[0].id,
        "item": items[0],
    }


# ── 5. Inbox (NV — any role) — PHẢI đặt trước /{id} để FastAPI match đúng

@router.get("/inbox")
def my_inbox(
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    status_filter: Optional[str] = Query(None, alias="status"),
    tab: Optional[str] = Query(None, description="waiting|working|finished"),
) -> dict:
    q = db.query(Directive).filter(Directive.to_user == user.username)

    tab_statuses = _resolve_tab(tab)
    if tab_statuses is not None:
        q = q.filter(Directive.status.in_(tab_statuses))
    else:
        statuses = _normalize_status_filter(status_filter)
        if statuses is not None:
            q = q.filter(Directive.status.in_(statuses))

    rows = q.order_by(Directive.created_at.desc()).limit(500).all()
    name_map = _bulk_names(db, [r.from_user for r in rows]) if rows else {}
    tep_map = _ds_tep_nhieu([r.id for r in rows])
    return {"total": len(rows), "items": [_to_dict(r, name_map, tep_map=tep_map) for r in rows]}


# ── 3. Detail ──────────────────────────────────────────────────────────────

@router.get("/{id}")
def get_directive(
    id: int,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    d = db.get(Directive, id)
    if not d:
        raise HTTPException(404, "Task không tồn tại")
    # Chỉ super, người giao, hoặc người nhận xem được
    if not _is_super(user) and user.username not in (d.from_user, d.to_user):
        raise HTTPException(403, "Không có quyền xem task này")
    name_map, pb_map = _bulk_names_pb(db, [d.from_user, d.to_user])
    return _to_dict(d, name_map, pb_map)


# ── 4. Close (CEO hoặc người giao) — semantic mới: 'cancelled' ────────────

@router.post("/{id}/close")
def close_directive(
    id: int,
    body: CloseBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """CEO/from_user huỷ task hẳn.

    Semantic mới: chỉ dùng để 'cancelled'. Body cũ 'dropped' → map về 'cancelled'.
    'done' vẫn cho phép (deprecate) — UI mới nên dùng `/complete` (NV) hoặc
    không close 'done' từ phía CEO; chỉ dùng `/reopen` để mở lại.
    """
    d = db.get(Directive, id)
    if not d:
        raise HTTPException(404, "Task không tồn tại")
    if not _is_super(user) and user.username != d.from_user:
        raise HTTPException(403, "Chỉ CEO hoặc người giao mới đóng được task")
    if body.status not in VALID_CLOSE_INPUT:
        raise HTTPException(400, "status close phải là 'cancelled' (hoặc legacy 'dropped'/'done')")

    # Map status input → v2
    raw = body.status
    if raw in ("dropped", "cancelled"):
        new_status = STATUS_CANCELLED
    else:  # 'done' — deprecate nhưng chấp nhận
        new_status = STATUS_DONE

    if d.status in (STATUS_DONE, STATUS_CANCELLED):
        raise HTTPException(400, f"Task đã ở '{d.status}', không thể đóng lại")

    now = _now_utc()
    d.status = new_status
    d.closed_at = now
    if new_status == STATUS_DONE:
        d.completed_at = d.completed_at or now
    d.last_activity_at = now
    if body.note:
        prefix = f"[CEO close — {new_status}] "
        d.response = _append_response(d.response, prefix, body.note)
    db.flush()
    _notify_closed(db, d, by=user.username, note=body.note or "")
    db.commit()

    # Status đổi sang done/cancelled → xoá event deadline (fail-soft)
    try:
        from shared.services.calendar_sync import delete_event_by_source
        if delete_event_by_source(db, "directive", str(d.id)):
            db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    log_action(
        db, app=d.app or "ceo", action="close_directive", user=user, request=request,
        resource=f"directive:{d.id}",
        payload={"status": new_status, "input_status": raw, "note": body.note},
    )
    # Real-time: Mai DM CEO báo việc đã đóng (fail-soft, không block response).
    try:
        from ceo.app.ai_brief.reminders import notify_ceo_directive_closed
        notify_ceo_directive_closed(db, d.id)
    except Exception:
        pass
    return {"ok": True, "id": d.id, "status": d.status}


# ── 4b. Delete task (chỉ người giao hoặc CEO/admin) ────────────────────────

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_directive(
    id: int,
    request: Request,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Xoá hẳn task (hard delete).

    - CEO/admin/assistant_ceo: xoá mọi task
    - Manager/Leader: chỉ xoá task của chính mình giao
    - NV (người nhận): không được xoá
    """
    d = db.get(Directive, id)
    if not d:
        raise HTTPException(404, "Task không tồn tại")
    if not _is_super(user) and user.username != d.from_user:
        raise HTTPException(403, "Chỉ CEO hoặc người giao task mới được xoá")
    to_user = d.to_user
    app_name = d.app or "ceo"
    # Xoá CalendarEvent gắn directive trước khi delete entity (fail-soft)
    try:
        from shared.services.calendar_sync import delete_event_by_source
        delete_event_by_source(db, "directive", str(d.id))
    except Exception:
        pass
    db.delete(d)
    db.flush()
    # Notify NV người nhận biết task đã bị xoá
    try:
        from shared.services.notify import notify
        notify(
            db, target=to_user, source_app=app_name,
            event_type="directive:deleted",
            title=f"[Giao Việc #{id}] Đã bị xoá",
            message=f"Task '{d.title}' bị xoá bởi {_ten_cua(db, user.username)}",
            ref_type="directive", ref_id=id, severity="warning",
            created_by=user.username,
        )
    except Exception:
        pass
    db.commit()
    # Task đã xoá khỏi DB thì tệp của nó không còn đường nào mở được — dọn luôn thư mục.
    shutil.rmtree(_tep_dir(id), ignore_errors=True)
    log_action(
        db, app=app_name, action="delete_directive", user=user, request=request,
        resource=f"directive:{id}",
    )


# ── 6. Respond (NV) ────────────────────────────────────────────────────────

@router.post("/{id}/respond")
def respond_directive(
    id: int,
    body: RespondBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    d = db.get(Directive, id)
    if not d:
        raise HTTPException(404, "Task không tồn tại")
    if d.to_user != user.username:
        raise HTTPException(403, "Chỉ người nhận task mới phản hồi")
    d.response = body.response
    d.last_activity_at = _now_utc()
    db.commit()
    log_action(
        db, app=d.app or "ceo", action="respond_directive", user=user, request=request,
        resource=f"directive:{d.id}",
    )
    name_map = _bulk_names(db, [d.from_user, d.to_user])
    return {"ok": True, "id": d.id, "item": _to_dict(d, name_map)}


# ── 7. v2 lifecycle endpoints ──────────────────────────────────────────────

@router.post("/{id}/ack")
def ack_directive(
    id: int,
    request: Request,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """NV bấm 'Đã nhận' — set acknowledged_at, status không đổi (vẫn 'assigned')."""
    d = db.get(Directive, id)
    if not d:
        raise HTTPException(404, "Task không tồn tại")
    _ensure_recipient(d, user)
    if d.status != STATUS_ASSIGNED:
        raise HTTPException(400, f"Task đang ở '{d.status}' — chỉ xác nhận được khi 'assigned'")
    now = _now_utc()
    if not d.acknowledged_at:
        d.acknowledged_at = now
    d.last_activity_at = now
    db.commit()
    db.refresh(d)
    log_action(
        db, app=d.app or "ceo", action="ack_directive", user=user, request=request,
        resource=f"directive:{d.id}",
    )
    try:
        _notify_status_change(
            db, d, by=user.username, event="acknowledged",
            message=f"{_ten_cua(db, user.username)} đã xác nhận nhận việc",
            severity="info",
        )
        db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass
    name_map = _bulk_names(db, [d.from_user, d.to_user])
    return {"ok": True, "id": d.id, "item": _to_dict(d, name_map)}


@router.post("/{id}/start")
def start_directive(
    id: int,
    request: Request,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """NV bấm 'Bắt đầu' — assigned → in_progress, set started_at (lần đầu)."""
    d = db.get(Directive, id)
    if not d:
        raise HTTPException(404, "Task không tồn tại")
    _ensure_recipient(d, user)
    if d.status != STATUS_ASSIGNED:
        raise HTTPException(400, f"Task đang ở '{d.status}' — chỉ bắt đầu được khi 'assigned'")
    now = _now_utc()
    d.status = STATUS_IN_PROGRESS
    if not d.started_at:
        d.started_at = now
    if not d.acknowledged_at:
        d.acknowledged_at = now
    d.last_activity_at = now
    db.commit()
    db.refresh(d)
    log_action(
        db, app=d.app or "ceo", action="start_directive", user=user, request=request,
        resource=f"directive:{d.id}",
    )
    try:
        _notify_status_change(
            db, d, by=user.username, event="started",
            message=f"{_ten_cua(db, user.username)} đã bắt đầu thực hiện",
            severity="info",
        )
        db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass
    name_map = _bulk_names(db, [d.from_user, d.to_user])
    return {"ok": True, "id": d.id, "item": _to_dict(d, name_map)}


@router.post("/{id}/pause")
def pause_directive(
    id: int,
    body: PauseBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """NV bấm 'Tạm dừng' — in_progress → blocked + reason."""
    d = db.get(Directive, id)
    if not d:
        raise HTTPException(404, "Task không tồn tại")
    _ensure_recipient(d, user)
    if d.status != STATUS_IN_PROGRESS:
        raise HTTPException(400, f"Task đang ở '{d.status}' — chỉ tạm dừng được khi 'in_progress'")
    reason = (body.reason or "").strip()
    if not reason:
        raise HTTPException(400, "Phải nhập lý do tạm dừng")
    now = _now_utc()
    d.status = STATUS_BLOCKED
    d.blocked_at = now
    d.blocked_reason = reason
    d.last_activity_at = now
    db.commit()
    db.refresh(d)
    log_action(
        db, app=d.app or "ceo", action="pause_directive", user=user, request=request,
        resource=f"directive:{d.id}",
        payload={"reason": reason},
    )
    try:
        _notify_status_change(
            db, d, by=user.username, event="blocked",
            message=f"{_ten_cua(db, user.username)} tạm dừng — lý do: {reason}",
            severity="warning",
        )
        db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass
    name_map = _bulk_names(db, [d.from_user, d.to_user])
    return {"ok": True, "id": d.id, "item": _to_dict(d, name_map)}


@router.post("/{id}/resume")
def resume_directive(
    id: int,
    request: Request,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """NV bấm 'Tiếp tục' — blocked → in_progress, clear blocked_reason."""
    d = db.get(Directive, id)
    if not d:
        raise HTTPException(404, "Task không tồn tại")
    _ensure_recipient(d, user)
    if d.status != STATUS_BLOCKED:
        raise HTTPException(400, f"Task đang ở '{d.status}' — chỉ tiếp tục được khi 'blocked'")
    now = _now_utc()
    d.status = STATUS_IN_PROGRESS
    d.blocked_reason = None
    d.last_activity_at = now
    db.commit()
    db.refresh(d)
    log_action(
        db, app=d.app or "ceo", action="resume_directive", user=user, request=request,
        resource=f"directive:{d.id}",
    )
    try:
        _notify_status_change(
            db, d, by=user.username, event="resumed",
            message=f"{_ten_cua(db, user.username)} đã tiếp tục công việc",
            severity="info",
        )
        db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass
    name_map = _bulk_names(db, [d.from_user, d.to_user])
    return {"ok": True, "id": d.id, "item": _to_dict(d, name_map)}


@router.post("/{id}/complete")
def complete_directive(
    id: int,
    body: CompleteBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """NV bấm 'Hoàn thành' — in_progress → done.

    Set completed_at + closed_at + last_activity_at = NOW().
    Append response (nếu đã có response cũ thì nối thêm).
    Hook realtime: notify_ceo_directive_closed (DM CEO).
    """
    d = db.get(Directive, id)
    if not d:
        raise HTTPException(404, "Task không tồn tại")
    _ensure_recipient(d, user)
    if d.status != STATUS_IN_PROGRESS:
        raise HTTPException(400, f"Task đang ở '{d.status}' — chỉ hoàn thành được khi 'in_progress'")
    response_text = (body.response or "").strip()
    if not response_text:
        raise HTTPException(400, "Phải nhập kết quả hoàn thành")
    now = _now_utc()
    d.status = STATUS_DONE
    d.completed_at = now
    d.closed_at = now
    d.last_activity_at = now
    prefix = f"[{_ten_cua(db, user.username)} hoàn thành] "
    d.response = _append_response(d.response, prefix, response_text)
    db.commit()
    db.refresh(d)

    # Cleanup calendar event (fail-soft)
    try:
        from shared.services.calendar_sync import delete_event_by_source
        if delete_event_by_source(db, "directive", str(d.id)):
            db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass

    log_action(
        db, app=d.app or "ceo", action="complete_directive", user=user, request=request,
        resource=f"directive:{d.id}",
        payload={"response_len": len(response_text)},
    )
    # Realtime DM CEO (fail-soft)
    try:
        from ceo.app.ai_brief.reminders import notify_ceo_directive_closed
        notify_ceo_directive_closed(db, d.id)
    except Exception:
        pass
    # Notify from_user (in-app)
    try:
        _notify_status_change(
            db, d, by=user.username, event="completed",
            message=f"{_ten_cua(db, user.username)} đã hoàn thành — kết quả: {response_text[:200]}",
            severity="success",
        )
        db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass

    name_map = _bulk_names(db, [d.from_user, d.to_user])
    return {"ok": True, "id": d.id, "item": _to_dict(d, name_map)}


@router.post("/{id}/reopen")
def reopen_directive(
    id: int,
    body: ReopenBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """CEO/from_user/super mở lại task đã 'done' → quay về 'in_progress'.

    Clear completed_at + closed_at, append reason vào response, update last_activity_at.
    """
    d = db.get(Directive, id)
    if not d:
        raise HTTPException(404, "Task không tồn tại")
    if not _is_super(user) and user.username != d.from_user:
        raise HTTPException(403, "Chỉ CEO hoặc người giao task mới mở lại được")
    if d.status != STATUS_DONE:
        raise HTTPException(400, f"Task đang ở '{d.status}' — chỉ mở lại được khi 'done'")
    reason = (body.reason or "").strip()
    if not reason:
        raise HTTPException(400, "Phải nhập lý do mở lại task")
    now = _now_utc()
    d.status = STATUS_IN_PROGRESS
    d.completed_at = None
    d.closed_at = None
    d.last_activity_at = now
    prefix = f"[{_ten_cua(db, user.username)} reopen] "
    d.response = _append_response(d.response, prefix, reason)
    db.commit()
    db.refresh(d)

    log_action(
        db, app=d.app or "ceo", action="reopen_directive", user=user, request=request,
        resource=f"directive:{d.id}",
        payload={"reason": reason},
    )
    # Notify NV người nhận biết task được mở lại
    try:
        from shared.services.notify import notify
        notify(
            db, target=d.to_user, source_app=d.app or "ceo",
            event_type="directive:reopened",
            title=f"[Giao Việc #{d.id}] Task được mở lại",
            message=f"{_ten_cua(db, user.username)} mở lại — lý do: {reason}",
            ref_type="directive", ref_id=d.id, url=f"/giao-viec#id={d.id}",
            severity="warning", created_by=user.username,
        )
        db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass

    name_map = _bulk_names(db, [d.from_user, d.to_user])
    return {"ok": True, "id": d.id, "item": _to_dict(d, name_map)}


# ── 8. Tệp đính kèm (12/09/2026) — tải lên · mở · xoá ──────────────────────
# Quyền: tải lên = người giao, người nhận, super · mở = như GET /{id} · xoá = người giao, super.

@router.post("/{id}/tep", response_model=TepOut, status_code=status.HTTP_201_CREATED)
def upload_tep(
    id: int,
    request: Request,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
) -> dict:
    """Tải một tệp lên task (multipart, field `file`).

    `def` thường (không async) như các endpoint khác trong file: FastAPI chạy nó trong threadpool
    nên đọc tệp và truy vấn DB đồng bộ không chặn event loop.
    """
    d = db.get(Directive, id)
    if not d:
        raise HTTPException(404, "Task không tồn tại")
    if not _is_super(user) and user.username not in (d.from_user, d.to_user):
        raise HTTPException(403, "Chỉ người giao, người nhận task hoặc CEO/admin mới tải tệp lên được")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _TEP_MIME:
        raise HTTPException(400, "Chỉ nhận tệp PDF, Word (DOC, DOCX), Excel (XLS, XLSX), JPG, PNG")
    if len(_ds_tep(id)) >= _TEP_TOI_DA:
        raise HTTPException(400, f"Mỗi task tối đa {_TEP_TOI_DA} tệp")
    # Đọc tối đa _TEP_MAX + 1 byte: đủ biết tệp vượt giới hạn mà không nạp cả tệp lớn vào RAM.
    data = file.file.read(_TEP_MAX + 1)
    if not data:
        raise HTTPException(400, "Tệp trống")
    if len(data) > _TEP_MAX:
        raise HTTPException(413, "Tệp quá lớn — tối đa 10MB")
    thu_muc = _tep_dir(id)
    thu_muc.mkdir(parents=True, exist_ok=True)
    ma = f"{uuid.uuid4().hex[:12]}__{_ten_goc_an_toan(file.filename, ext)}"
    (thu_muc / ma).write_bytes(data)
    log_action(
        db, app=d.app or "ceo", action="upload_directive_tep", user=user, request=request,
        resource=f"directive:{d.id}",
        payload={"ma": ma, "kich_thuoc": len(data)},
    )
    return _tep_item(id, ma, len(data))


@router.get("/{id}/tep/{ma}", response_class=FileResponse)
def xem_tep(
    id: int,
    ma: str,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Mở tệp inline — ai xem được task (GET /{id}) thì mở được tệp của task."""
    if not _TEP_MA_RE.match(ma):
        raise HTTPException(400, "Tên tệp không hợp lệ")
    d = db.get(Directive, id)
    if not d:
        raise HTTPException(404, "Task không tồn tại")
    if not _is_super(user) and user.username not in (d.from_user, d.to_user):
        raise HTTPException(403, "Không có quyền xem tệp của task này")
    thu_muc = _tep_dir(id)
    f = (thu_muc / ma).resolve()
    # resolve() rồi so thư mục cha: chặn tên tệp tìm cách thoát ra ngoài thư mục của task.
    if f.parent != thu_muc or not f.is_file():
        raise HTTPException(404, "Tệp không tồn tại")
    # Starlette tự viết `filename*=utf-8''…` (RFC 5987) khi tên có dấu tiếng Việt.
    # nosniff: tệp do người dùng tải lên — không cho trình duyệt đoán kiểu khác media type đã khai.
    return FileResponse(
        str(f), filename=ma.split("__", 1)[1], content_disposition_type="inline",
        media_type=_TEP_MIME.get(f.suffix.lower()),
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{id}/tep", status_code=status.HTTP_204_NO_CONTENT)
def xoa_tep(
    id: int,
    request: Request,
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    ma: str = Query(..., description="giá trị `ma` trong tep_dinh_kem"),
):
    """Xoá một tệp. Người giao task hoặc CEO/admin — người nhận không xoá được."""
    if not _TEP_MA_RE.match(ma):
        raise HTTPException(400, "Tên tệp không hợp lệ")
    d = db.get(Directive, id)
    if not d:
        raise HTTPException(404, "Task không tồn tại")
    if not _is_super(user) and user.username != d.from_user:
        raise HTTPException(403, "Chỉ người giao task hoặc CEO/admin mới xoá được tệp")
    thu_muc = _tep_dir(id)
    f = (thu_muc / ma).resolve()
    if f.parent != thu_muc or not f.is_file():
        raise HTTPException(404, "Tệp không tồn tại")
    f.unlink()
    log_action(
        db, app=d.app or "ceo", action="delete_directive_tep", user=user, request=request,
        resource=f"directive:{d.id}", payload={"ma": ma},
    )
