"""Support / Service Desk — shared router mount trong 8 app.

Mount prefix: /support (HTML page) và /api/support (JSON API).

Endpoints:
    HTML:
      GET  /support               — SPA-lite page (default view = "Ticket của tôi")
      GET  /support/new           — SPA page mở tab "Tạo mới"
      GET  /support/{id}          — SPA page mở tab "Chi tiết"

    API:
      POST /api/support/tickets                 — raise ticket (multipart, kèm ảnh)
      GET  /api/support/tickets/mine            — list ticket mình raise
      GET  /api/support/tickets/{id}            — chi tiết (raiser hoặc CN)
      POST /api/support/tickets/{id}/status     — CN đổi trạng thái workflow
      POST /api/support/tickets/{id}/bug-status — CN đổi trạng thái bug
      GET  /api/support/uploads/{scope}/{fname} — serve ảnh đính kèm

Phân quyền:
    - Raiser: chỉ xem của mình
    - User có 'congnghe' trong apps (phòng CN) hoặc super role: xem tất, sửa được
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status,
)
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import case, select, text as sql_text
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload, current_user
from shared.db import get_db
from shared.services.notify import notify_many
from shared.templates import _lookup_user_info, user_ctx
from shared.utils.uploads import ALLOWED_IMAGE_TYPES, resolve_path, save_upload


def _user_info(_db, username: str) -> dict:
    """Wrapper: shared._lookup_user_info(username) returns tuple, we want dict.

    First arg (_db) kept for backward-compat with earlier drafts of this file.
    """
    if not username:
        return {"ho_ten": "", "phong_ban": "", "email": "", "chuc_vu": ""}
    t = _lookup_user_info(username)
    return {"ho_ten": t[0], "phong_ban": t[1], "email": t[2], "chuc_vu": t[3]}


router = APIRouter()
_USER = Depends(current_user)

# Root templates + static (relative to shared/)
_SHARED_DIR = Path(__file__).resolve().parent.parent
_TEMPLATES_DIR = _SHARED_DIR / "templates"
_STATIC_DIR = _SHARED_DIR / "static"
_templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_LOAI = frozenset({"bug", "feature", "nang_cap", "cach_dung"})
_UU_TIEN = frozenset({"khan", "cao", "vua", "thap"})
_TRANG_THAI = frozenset({"moi", "tiep_nhan", "dang_xu_ly", "cho_phan_hoi", "da_xu_ly", "dong"})
_BUG_STATUS = frozenset({"chua_tai_hien", "da_tai_hien", "dang_debug", "da_fix", "da_deploy", "qa_verified"})

# Ai được xem tất / sửa
_CN_ROLES = frozenset({"admin", "ceo", "assistant_ceo"})

# SLA theo mức ưu tiên: (hạn phản hồi, hạn xử lý)
_SLA = {
    "khan": (timedelta(minutes=30), timedelta(hours=4)),
    "cao":  (timedelta(hours=2),    timedelta(days=1)),
    "vua":  (timedelta(days=1),     timedelta(days=3)),
    "thap": (timedelta(days=2),     None),
}

_UU_TIEN_RANK = {"khan": 0, "cao": 1, "vua": 2, "thap": 3}


def _is_cn(user: JWTPayload) -> bool:
    """User thuộc phòng Công Nghệ (xem/sửa được mọi ticket)."""
    if (user.role or "").lower() in _CN_ROLES:
        return True
    return "congnghe" in [a.lower() for a in (user.apps or []) if a]


def _resolve_app_source(request: Request) -> str:
    """Đoán app đang mount router từ Host header hoặc từ app.title.

    Ưu tiên: state.app_name (set trong main.py), fallback từ Host header.
    """
    st = getattr(request.app.state, "app_name", None)
    if st:
        return str(st).lower()
    host = (request.headers.get("host") or "").split(":")[0].lower()
    for sub in ("baogia", "marketing", "muahang", "hcns", "ketoan", "saleadmin", "ceo", "itque"):
        if host.startswith(sub + "."):
            return "congnghe" if sub == "itque" else sub
    return "unknown"


# ── Schemas ─────────────────────────────────────────────────────────────

class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tieu_de: str
    mo_ta: Optional[str] = None
    loai: str
    muc_uu_tien: str
    trang_thai: str
    app_source: Optional[str] = None
    nguoi_bao: Optional[str] = None
    phong_ban_bao: Optional[str] = None
    nguoi_xu_ly: Optional[str] = None
    sla_phan_hoi_han: Optional[datetime] = None
    sla_xu_ly_han: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    attachments: list = []
    created_at: datetime
    updated_at: datetime
    # enriched
    nguoi_bao_ho_ten: Optional[str] = None
    nguoi_bao_phong_ban: Optional[str] = None
    nguoi_xu_ly_ho_ten: Optional[str] = None
    bug_status: Optional[str] = None


class StatusChange(BaseModel):
    trang_thai: str

    @field_validator("trang_thai")
    @classmethod
    def _v(cls, v: str) -> str:
        if v not in _TRANG_THAI:
            raise ValueError(f"trang_thai must be one of {_TRANG_THAI}")
        return v


class BugStatusChange(BaseModel):
    bug_status: str

    @field_validator("bug_status")
    @classmethod
    def _v(cls, v: str) -> str:
        if v not in _BUG_STATUS:
            raise ValueError(f"bug_status must be one of {_BUG_STATUS}")
        return v


# ── Helper: fetch ticket as dict với enrich ──────────────────────────────

def _ticket_row_to_dict(db: Session, row) -> dict:
    d = {
        "id": row["id"] if hasattr(row, "keys") else row.id,
        "tieu_de": row["tieu_de"] if hasattr(row, "keys") else row.tieu_de,
        "mo_ta": row["mo_ta"] if hasattr(row, "keys") else row.mo_ta,
        "loai": row["loai"] if hasattr(row, "keys") else row.loai,
        "muc_uu_tien": row["muc_uu_tien"] if hasattr(row, "keys") else row.muc_uu_tien,
        "trang_thai": row["trang_thai"] if hasattr(row, "keys") else row.trang_thai,
        "bug_status": (row["bug_status"] if hasattr(row, "keys") else getattr(row, "bug_status", None)),
        "app_source": row["app_source"] if hasattr(row, "keys") else row.app_source,
        "app_id": row["app_id"] if hasattr(row, "keys") else row.app_id,
        "nguoi_bao": row["nguoi_bao"] if hasattr(row, "keys") else row.nguoi_bao,
        "phong_ban_bao": row["phong_ban_bao"] if hasattr(row, "keys") else row.phong_ban_bao,
        "nguoi_xu_ly": row["nguoi_xu_ly"] if hasattr(row, "keys") else row.nguoi_xu_ly,
        "sla_phan_hoi_han": _iso(row["sla_phan_hoi_han"] if hasattr(row, "keys") else row.sla_phan_hoi_han),
        "sla_xu_ly_han": _iso(row["sla_xu_ly_han"] if hasattr(row, "keys") else row.sla_xu_ly_han),
        "closed_at": _iso(row["closed_at"] if hasattr(row, "keys") else row.closed_at),
        "attachments": (row["attachments"] if hasattr(row, "keys") else row.attachments) or [],
        "created_at": _iso(row["created_at"] if hasattr(row, "keys") else row.created_at),
        "updated_at": _iso(row["updated_at"] if hasattr(row, "keys") else row.updated_at),
    }
    # Enrich tên hiển thị
    row_nguoi_bao = d["nguoi_bao"]
    row_nguoi_xu_ly = d["nguoi_xu_ly"]
    if row_nguoi_bao:
        info = _user_info(db, row_nguoi_bao) or {}
        d["nguoi_bao_ho_ten"] = info.get("ho_ten") or row_nguoi_bao
        d["nguoi_bao_phong_ban"] = info.get("phong_ban")
    if row_nguoi_xu_ly:
        info = _user_info(db, row_nguoi_xu_ly) or {}
        d["nguoi_xu_ly_ho_ten"] = info.get("ho_ten") or row_nguoi_xu_ly
    return d


def _iso(v):
    return v.isoformat() if v else None


def _fetch_ticket(db: Session, tid: int):
    """Raw SQL fetch avoids ORM model version issues."""
    row = db.execute(
        sql_text(
            "SELECT id, tieu_de, mo_ta, loai, muc_uu_tien, trang_thai, bug_status, "
            "app_source, app_id, nguoi_bao, phong_ban_bao, nguoi_xu_ly, "
            "sla_phan_hoi_han, sla_xu_ly_han, closed_at, attachments, "
            "created_at, updated_at "
            "FROM congnghe.cn_tickets WHERE id = :id"
        ),
        {"id": tid},
    ).mappings().first()
    return row


# ── API: raise ticket ────────────────────────────────────────────────────

@router.post("/api/support/tickets", response_model=None)
async def raise_ticket(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _USER],
    tieu_de: str = Form(...),
    mo_ta: str = Form(""),
    loai: str = Form("bug"),
    muc_uu_tien: str = Form("vua"),
    images: List[UploadFile] = File(default=[]),
):
    tieu_de = (tieu_de or "").strip()
    if not tieu_de or len(tieu_de) < 4:
        raise HTTPException(400, "Tiêu đề tối thiểu 4 ký tự")
    if len(tieu_de) > 200:
        raise HTTPException(400, "Tiêu đề tối đa 200 ký tự")
    if loai not in _LOAI:
        raise HTTPException(400, f"Loại không hợp lệ (bug/feature/nang_cap/cach_dung)")
    if muc_uu_tien not in _UU_TIEN:
        raise HTTPException(400, f"Mức ưu tiên không hợp lệ (khan/cao/vua/thap)")

    app_source = _resolve_app_source(request)
    now = datetime.now(timezone.utc)
    ph, xl = _SLA.get(muc_uu_tien, (None, None))

    # Lookup phong_ban_bao từ HCNS
    info = _user_info(db, user.username) or {}
    phong_ban_bao = info.get("phong_ban") or ""

    # Insert ticket
    res = db.execute(
        sql_text(
            "INSERT INTO congnghe.cn_tickets "
            "(tieu_de, mo_ta, loai, muc_uu_tien, trang_thai, app_source, "
            " nguoi_bao, phong_ban_bao, sla_phan_hoi_han, sla_xu_ly_han) "
            "VALUES (:tieu_de, :mo_ta, :loai, :uu_tien, 'moi', :app_source, "
            " :nguoi_bao, :pb, :sla_ph, :sla_xl) "
            "RETURNING id, created_at"
        ),
        {
            "tieu_de": tieu_de,
            "mo_ta": (mo_ta or "").strip() or None,
            "loai": loai,
            "uu_tien": muc_uu_tien,
            "app_source": app_source,
            "nguoi_bao": user.username,
            "pb": phong_ban_bao,
            "sla_ph": (now + ph) if ph else None,
            "sla_xl": (now + xl) if xl else None,
        },
    ).first()
    if not res:
        raise HTTPException(500, "Không tạo được ticket")
    ticket_id = res[0]

    # Save uploaded images
    attach_list: list[dict] = []
    if images:
        for f in images:
            if not f or not f.filename:
                continue
            try:
                scope = f"ticket_{ticket_id}"
                fname, _url, size = await save_upload(
                    f, app="support", scope=scope, allow_docs=False,
                )
                # save_upload trả URL /api/uploads/{scope}/{fname} — override
                # thành /api/support/uploads/{scope}/{fname} để KHÔNG đụng
                # route /api/uploads/* của app host.
                url = f"/api/support/uploads/{scope}/{fname}"
                attach_list.append({
                    "filename": fname,
                    "orig_name": f.filename[:120],
                    "url": url,
                    "size_bytes": size,
                    "content_type": f.content_type,
                    "uploaded_at": now.isoformat(),
                })
            except HTTPException as e:
                # Bỏ qua file lỗi, không rollback cả ticket
                attach_list.append({"error": str(e.detail), "orig_name": f.filename[:120]})

    if attach_list:
        db.execute(
            sql_text(
                "UPDATE congnghe.cn_tickets SET attachments = CAST(:att AS jsonb) "
                "WHERE id = :id"
            ),
            {"att": _jsonify(attach_list), "id": ticket_id},
        )

    # Fan-out noti tới toàn team CN (user nào có 'congnghe' trong apps)
    cn_users = db.execute(
        sql_text(
            "SELECT username FROM shared.users "
            "WHERE active = true AND ('congnghe' = ANY(apps) OR role IN ('admin','ceo','assistant_ceo'))"
        )
    ).scalars().all()
    if cn_users:
        raiser_display = info.get("ho_ten") or user.username
        _ = notify_many(
            db,
            targets=[u for u in cn_users if u and u != user.username],
            source_app="congnghe",
            event_type="support_ticket_new",
            title=f"Ticket mới #{ticket_id} · {muc_uu_tien.upper()}",
            message=f"{raiser_display} ({app_source}): {tieu_de}",
            ref_type="cn_ticket",
            ref_id=str(ticket_id),
            url=f"/support/{ticket_id}",
            severity="warn" if muc_uu_tien in ("khan", "cao") else "info",
            created_by=user.username,
        )

    log_action(
        db, app=app_source, action="support_raise_ticket", user=user, request=request,
        resource=f"cn_ticket:{ticket_id}",
        payload={"loai": loai, "muc_uu_tien": muc_uu_tien, "n_images": len(attach_list)},
    )
    db.commit()

    row = _fetch_ticket(db, ticket_id)
    return _ticket_row_to_dict(db, row)


def _jsonify(v) -> str:
    """Serialize list/dict for jsonb cast."""
    import json
    return json.dumps(v, ensure_ascii=False, default=str)


# ── API: list mine ───────────────────────────────────────────────────────

@router.get("/api/support/tickets/mine")
def list_mine(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _USER],
    trang_thai: Optional[str] = None,
    limit: int = 50,
):
    limit = max(1, min(200, int(limit or 50)))
    q = (
        "SELECT id, tieu_de, mo_ta, loai, muc_uu_tien, trang_thai, bug_status, "
        "app_source, app_id, nguoi_bao, phong_ban_bao, nguoi_xu_ly, "
        "sla_phan_hoi_han, sla_xu_ly_han, closed_at, attachments, "
        "created_at, updated_at "
        "FROM congnghe.cn_tickets "
        "WHERE nguoi_bao = :me "
    )
    params = {"me": user.username, "lim": limit}
    if trang_thai and trang_thai in _TRANG_THAI:
        q += "AND trang_thai = :st "
        params["st"] = trang_thai
    q += "ORDER BY updated_at DESC LIMIT :lim"

    rows = db.execute(sql_text(q), params).mappings().all()

    # Enrich raiser info once (cùng user)
    my_info = _user_info(db, user.username) or {}
    my_ho_ten = my_info.get("ho_ten") or user.username

    # Batch lookup người xử lý
    xu_ly_names = set(r["nguoi_xu_ly"] for r in rows if r.get("nguoi_xu_ly"))
    xu_ly_map = {}
    for xn in xu_ly_names:
        i = _user_info(db, xn) or {}
        xu_ly_map[xn] = i.get("ho_ten") or xn

    # Counts breakdown (only my tickets)
    counts_rows = db.execute(
        sql_text(
            "SELECT trang_thai, count(*) AS n FROM congnghe.cn_tickets "
            "WHERE nguoi_bao = :me GROUP BY trang_thai"
        ),
        {"me": user.username},
    ).mappings().all()
    counts = {r["trang_thai"]: r["n"] for r in counts_rows}
    total = sum(counts.values())

    return {
        "items": [
            {
                "id": r["id"],
                "tieu_de": r["tieu_de"],
                "loai": r["loai"],
                "muc_uu_tien": r["muc_uu_tien"],
                "trang_thai": r["trang_thai"],
                "bug_status": r["bug_status"],
                "app_source": r["app_source"],
                "nguoi_bao": r["nguoi_bao"],
                "nguoi_bao_ho_ten": my_ho_ten,
                "nguoi_xu_ly": r["nguoi_xu_ly"],
                "nguoi_xu_ly_ho_ten": xu_ly_map.get(r["nguoi_xu_ly"]),
                "n_attachments": len(r["attachments"] or []),
                "created_at": _iso(r["created_at"]),
                "updated_at": _iso(r["updated_at"]),
                "sla_xu_ly_han": _iso(r["sla_xu_ly_han"]),
            }
            for r in rows
        ],
        "count": len(rows),
        "counts": {
            "total": total,
            "moi": counts.get("moi", 0),
            "tiep_nhan": counts.get("tiep_nhan", 0),
            "dang_xu_ly": counts.get("dang_xu_ly", 0),
            "cho_phan_hoi": counts.get("cho_phan_hoi", 0),
            "da_xu_ly": counts.get("da_xu_ly", 0),
            "dong": counts.get("dong", 0),
        },
        "user": {
            "username": user.username,
            "ho_ten": my_ho_ten,
            "phong_ban": my_info.get("phong_ban"),
        },
    }


# ── API: list all (CN only) ──────────────────────────────────────────────

@router.get("/api/support/tickets")
def list_all(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _USER],
    trang_thai: Optional[str] = None,
    limit: int = 100,
):
    if not _is_cn(user):
        raise HTTPException(403, "Chỉ user phòng Công Nghệ xem được toàn bộ ticket")
    limit = max(1, min(500, int(limit or 100)))
    q = (
        "SELECT id, tieu_de, loai, muc_uu_tien, trang_thai, "
        "app_source, nguoi_bao, phong_ban_bao, nguoi_xu_ly, "
        "sla_xu_ly_han, closed_at, attachments, created_at, updated_at "
        "FROM congnghe.cn_tickets "
    )
    params = {"lim": limit}
    if trang_thai and trang_thai in _TRANG_THAI:
        q += "WHERE trang_thai = :st "
        params["st"] = trang_thai
    q += "ORDER BY CASE muc_uu_tien WHEN 'khan' THEN 0 WHEN 'cao' THEN 1 WHEN 'vua' THEN 2 ELSE 3 END, updated_at DESC LIMIT :lim"

    rows = db.execute(sql_text(q), params).mappings().all()

    # Batch lookup
    all_users = set()
    for r in rows:
        if r.get("nguoi_bao"): all_users.add(r["nguoi_bao"])
        if r.get("nguoi_xu_ly"): all_users.add(r["nguoi_xu_ly"])
    user_map = {}
    for u in all_users:
        info = _user_info(db, u) or {}
        user_map[u] = info.get("ho_ten") or u

    return {
        "items": [
            {
                "id": r["id"],
                "tieu_de": r["tieu_de"],
                "loai": r["loai"],
                "muc_uu_tien": r["muc_uu_tien"],
                "trang_thai": r["trang_thai"],
                "app_source": r["app_source"],
                "nguoi_bao": r["nguoi_bao"],
                "nguoi_bao_ho_ten": user_map.get(r["nguoi_bao"]),
                "phong_ban_bao": r["phong_ban_bao"],
                "nguoi_xu_ly": r["nguoi_xu_ly"],
                "nguoi_xu_ly_ho_ten": user_map.get(r["nguoi_xu_ly"]),
                "n_attachments": len(r["attachments"] or []),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
                "sla_xu_ly_han": r["sla_xu_ly_han"].isoformat() if r["sla_xu_ly_han"] else None,
            }
            for r in rows
        ],
        "count": len(rows),
    }


# ── API: detail (full: ticket + comments + events + related) ─────────

@router.get("/api/support/tickets/{tid}")
def get_ticket(
    tid: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _USER],
):
    row = _fetch_ticket(db, tid)
    if not row:
        raise HTTPException(404, "Ticket không tồn tại")
    if row["nguoi_bao"] != user.username and not _is_cn(user):
        raise HTTPException(403, "Không có quyền xem ticket này")

    d = _ticket_row_to_dict(db, row)

    # Comments: raiser only sees non-internal; CN sees all
    is_cn = _is_cn(user)
    q_cmt = (
        "SELECT id, ticket_id, username, noi_dung, is_noi_bo, created_at "
        "FROM congnghe.cn_ticket_comments WHERE ticket_id = :tid "
    )
    if not is_cn:
        q_cmt += "AND is_noi_bo = false "
    q_cmt += "ORDER BY created_at ASC"
    cmts = db.execute(sql_text(q_cmt), {"tid": tid}).mappings().all()
    # Enrich author name
    author_names = set(c["username"] for c in cmts if c["username"])
    author_map = {}
    for u in author_names:
        i = _user_info(db, u) or {}
        author_map[u] = i.get("ho_ten") or u

    d["comments"] = [
        {
            "id": c["id"],
            "username": c["username"],
            "ho_ten": author_map.get(c["username"]),
            "noi_dung": c["noi_dung"],
            "is_noi_bo": c["is_noi_bo"],
            "created_at": _iso(c["created_at"]),
            "is_cn_author": _is_cn_username(db, c["username"]) if c["username"] else False,
        }
        for c in cmts
    ]

    # Events: derived from ticket fields (created + status log via audit_log if present)
    events = [
        {"kind": "created", "when": d["created_at"], "actor": d["nguoi_bao"],
         "actor_ho_ten": d.get("nguoi_bao_ho_ten"),
         "text": f"tạo ticket từ {d.get('app_source') or 'unknown'}"},
    ]
    if d.get("nguoi_xu_ly"):
        events.append({"kind": "assigned", "when": d["updated_at"], "actor": d["nguoi_xu_ly"],
                       "actor_ho_ten": d.get("nguoi_xu_ly_ho_ten"),
                       "text": f"tiếp nhận ticket"})
    # Pull audit_log entries (column is `ts` not `created_at`)
    audit_rows = db.execute(
        sql_text(
            "SELECT action, username, ts, payload FROM shared.audit_log "
            "WHERE resource = :res ORDER BY ts ASC LIMIT 40"
        ),
        {"res": f"cn_ticket:{tid}"},
    ).mappings().all()
    for a in audit_rows:
        act = a["action"] or ""
        if act == "support_raise_ticket":
            continue  # already covered by "created"
        act_name = _user_info(db, a["username"]) if a["username"] else {}
        events.append({
            "kind": act,
            "when": _iso(a["ts"]),
            "actor": a["username"],
            "actor_ho_ten": act_name.get("ho_ten") if act_name else a["username"],
            "text": _describe_action(act, a["payload"]),
        })
    events.sort(key=lambda x: x.get("when") or "")
    d["events"] = events

    # Related tickets: same nguoi_bao + not this one, last 3
    rel_rows = db.execute(
        sql_text(
            "SELECT id, tieu_de, trang_thai, muc_uu_tien, loai, app_source, updated_at "
            "FROM congnghe.cn_tickets "
            "WHERE nguoi_bao = :me AND id != :id "
            "ORDER BY updated_at DESC LIMIT 3"
        ),
        {"me": d["nguoi_bao"], "id": tid},
    ).mappings().all()
    d["related"] = [
        {
            "id": r["id"],
            "tieu_de": r["tieu_de"],
            "trang_thai": r["trang_thai"],
            "muc_uu_tien": r["muc_uu_tien"],
            "loai": r["loai"],
            "app_source": r["app_source"],
            "updated_at": _iso(r["updated_at"]),
        }
        for r in rel_rows
    ]

    d["viewer_is_cn"] = is_cn
    return d


def _is_cn_username(db: Session, username: str) -> bool:
    """Check if a username belongs to CN team (for comment styling)."""
    if not username:
        return False
    row = db.execute(
        sql_text("SELECT role, apps FROM shared.users WHERE username = :u"),
        {"u": username},
    ).first()
    if not row:
        return False
    role, apps = row
    if (role or "").lower() in _CN_ROLES:
        return True
    return "congnghe" in [str(a).lower() for a in (apps or [])]


def _describe_action(action: str, payload) -> str:
    if action == "support_change_status":
        p = payload if isinstance(payload, dict) else {}
        st = (p or {}).get("trang_thai", "?")
        labels = {"moi": "Mới", "tiep_nhan": "Tiếp nhận", "dang_xu_ly": "Đang xử lý",
                  "cho_phan_hoi": "Chờ phản hồi", "da_xu_ly": "Đã xử lý", "dong": "Đóng"}
        return f"đổi trạng thái → {labels.get(st, st)}"
    if action == "support_change_bug_status":
        p = payload if isinstance(payload, dict) else {}
        bs = (p or {}).get("bug_status", "?")
        labels = {"chua_tai_hien": "Chưa tái hiện", "da_tai_hien": "Đã tái hiện",
                  "dang_debug": "Đang debug", "da_fix": "Đã fix",
                  "da_deploy": "Đã deploy", "qa_verified": "QA verified"}
        return f"đổi debug status → {labels.get(bs, bs)}"
    if action == "support_add_comment":
        p = payload if isinstance(payload, dict) else {}
        return "thêm ghi chú nội bộ" if (p or {}).get("is_noi_bo") else "trả lời"
    return action


# ── API: change status (CN only) ────────────────────────────────────────

@router.post("/api/support/tickets/{tid}/status")
def change_status(
    tid: int,
    body: StatusChange,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _USER],
):
    if not _is_cn(user):
        raise HTTPException(403, "Chỉ user phòng Công Nghệ đổi được trạng thái")
    row = _fetch_ticket(db, tid)
    if not row:
        raise HTTPException(404, "Ticket không tồn tại")

    new_st = body.trang_thai
    now = datetime.now(timezone.utc)
    closed_at = now if new_st == "dong" and not row["closed_at"] else (
        None if new_st != "dong" else row["closed_at"]
    )
    # Nếu chuyển sang trạng thái xử lý và chưa có nguoi_xu_ly → gán CN đang thao tác
    set_nxl = ""
    params = {"st": new_st, "id": tid, "closed_at": closed_at}
    if new_st in ("tiep_nhan", "dang_xu_ly") and not row["nguoi_xu_ly"]:
        set_nxl = ", nguoi_xu_ly = :xl"
        params["xl"] = user.username

    db.execute(
        sql_text(
            "UPDATE congnghe.cn_tickets SET trang_thai = :st, "
            "closed_at = :closed_at" + set_nxl + " "
            "WHERE id = :id"
        ),
        params,
    )

    # Notify raiser khi CN đổi trạng thái
    if row["nguoi_bao"] and row["nguoi_bao"] != user.username:
        st_label = {
            "moi": "Mới", "tiep_nhan": "Tiếp nhận", "dang_xu_ly": "Đang xử lý",
            "cho_phan_hoi": "Chờ phản hồi", "da_xu_ly": "Đã xử lý", "dong": "Đóng",
        }.get(new_st, new_st)
        notify_many(
            db,
            targets=[row["nguoi_bao"]],
            source_app=row["app_source"] or "congnghe",
            event_type="support_ticket_updated",
            title=f"Ticket #{tid} → {st_label}",
            message=f"{row['tieu_de'][:100]}",
            ref_type="cn_ticket",
            ref_id=str(tid),
            url=f"/support/{tid}",
            severity="info" if new_st != "dong" else "success",
            created_by=user.username,
        )

    log_action(
        db, app="congnghe", action="support_change_status", user=user, request=request,
        resource=f"cn_ticket:{tid}", payload={"trang_thai": new_st},
    )
    db.commit()
    return _ticket_row_to_dict(db, _fetch_ticket(db, tid))


# ── API: add comment ──────────────────────────────────────────────────

class CommentCreate(BaseModel):
    noi_dung: str
    is_noi_bo: bool = False


@router.post("/api/support/tickets/{tid}/comment")
def add_comment(
    tid: int,
    body: CommentCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _USER],
):
    txt = (body.noi_dung or "").strip()
    if not txt:
        raise HTTPException(400, "Nội dung không được để trống")
    if len(txt) > 5000:
        raise HTTPException(400, "Nội dung tối đa 5000 ký tự")
    row = _fetch_ticket(db, tid)
    if not row:
        raise HTTPException(404, "Ticket không tồn tại")

    is_cn = _is_cn(user)
    # Access
    if row["nguoi_bao"] != user.username and not is_cn:
        raise HTTPException(403, "Không có quyền comment ticket này")
    # Raiser không được ghi comment nội bộ
    is_noi_bo = bool(body.is_noi_bo) and is_cn

    res = db.execute(
        sql_text(
            "INSERT INTO congnghe.cn_ticket_comments (ticket_id, username, noi_dung, is_noi_bo) "
            "VALUES (:tid, :u, :n, :b) RETURNING id, created_at"
        ),
        {"tid": tid, "u": user.username, "n": txt, "b": is_noi_bo},
    ).first()
    if not res:
        raise HTTPException(500, "Không lưu được comment")

    # Bump ticket.updated_at
    db.execute(
        sql_text("UPDATE congnghe.cn_tickets SET updated_at = now() WHERE id = :id"),
        {"id": tid},
    )

    # Notify counter-party
    my_info = _user_info(db, user.username) or {}
    display = my_info.get("ho_ten") or user.username
    if is_cn:
        # CN vừa comment → noti raiser (chỉ nếu comment không phải nội bộ)
        if row["nguoi_bao"] and row["nguoi_bao"] != user.username and not is_noi_bo:
            notify_many(
                db,
                targets=[row["nguoi_bao"]],
                source_app=row["app_source"] or "congnghe",
                event_type="support_ticket_comment",
                title=f"Ticket #{tid} có phản hồi mới",
                message=f"{display}: {txt[:120]}",
                ref_type="cn_ticket",
                ref_id=str(tid),
                url=f"/support/{tid}",
                severity="info",
                created_by=user.username,
            )
    else:
        # Raiser vừa comment → noti CN team
        cn_users = db.execute(
            sql_text(
                "SELECT username FROM shared.users "
                "WHERE active = true AND ('congnghe' = ANY(apps) OR role IN ('admin','ceo','assistant_ceo'))"
            )
        ).scalars().all()
        if cn_users:
            notify_many(
                db,
                targets=[u for u in cn_users if u and u != user.username],
                source_app="congnghe",
                event_type="support_ticket_comment",
                title=f"Ticket #{tid} — raiser trả lời",
                message=f"{display}: {txt[:120]}",
                ref_type="cn_ticket",
                ref_id=str(tid),
                url=f"/support/{tid}",
                severity="info",
                created_by=user.username,
            )

    log_action(
        db, app="congnghe", action="support_add_comment", user=user, request=request,
        resource=f"cn_ticket:{tid}", payload={"is_noi_bo": is_noi_bo, "len": len(txt)},
    )
    db.commit()
    return {
        "id": res[0],
        "ticket_id": tid,
        "username": user.username,
        "ho_ten": display,
        "noi_dung": txt,
        "is_noi_bo": is_noi_bo,
        "created_at": _iso(res[1]),
        "is_cn_author": is_cn,
    }


# ── API: change bug_status (CN only) ─────────────────────────────────

@router.post("/api/support/tickets/{tid}/bug-status")
def change_bug_status(
    tid: int,
    body: BugStatusChange,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _USER],
):
    if not _is_cn(user):
        raise HTTPException(403, "Chỉ user phòng Công Nghệ đổi được bug status")
    row = _fetch_ticket(db, tid)
    if not row:
        raise HTTPException(404, "Ticket không tồn tại")
    if row["loai"] != "bug":
        raise HTTPException(400, "Ticket không phải loại 'bug'")
    db.execute(
        sql_text("UPDATE congnghe.cn_tickets SET bug_status = :bs WHERE id = :id"),
        {"bs": body.bug_status, "id": tid},
    )
    log_action(
        db, app="congnghe", action="support_change_bug_status", user=user, request=request,
        resource=f"cn_ticket:{tid}", payload={"bug_status": body.bug_status},
    )
    db.commit()
    return _ticket_row_to_dict(db, _fetch_ticket(db, tid))


# ── HTML page ──────────────────────────────────────────────────────────

def _render_support(request: Request, user: JWTPayload, initial_view: str, initial_tid: Optional[int] = None):
    app_source = _resolve_app_source(request)
    ctx = {
        "request": request,
        "user": user_ctx(user),
        "app_source": app_source,
        "is_cn": _is_cn(user),
        "initial_view": initial_view,
        "initial_tid": initial_tid or 0,
    }
    resp = _templates.TemplateResponse("support.html", ctx)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


# NOTE: static file routes phải đăng ký TRƯỚC `/support/{tid}` để FastAPI match literal path
@router.get("/support/static/support.css")
def serve_css():
    return FileResponse(str(_STATIC_DIR / "support.css"), media_type="text/css")


@router.get("/support/static/support.js")
def serve_js():
    return FileResponse(str(_STATIC_DIR / "support.js"), media_type="application/javascript")


@router.get("/support/static/logo.png")
def serve_logo():
    p = _STATIC_DIR / "logo.png"
    if p.exists():
        return FileResponse(str(p), media_type="image/png")
    raise HTTPException(404, "No logo")


@router.get("/support", response_class=HTMLResponse)
def page_support_mine(request: Request, user: Annotated[JWTPayload, _USER]):
    return _render_support(request, user, "mine")


@router.get("/support/new", response_class=HTMLResponse)
def page_support_new(request: Request, user: Annotated[JWTPayload, _USER]):
    return _render_support(request, user, "raise")


@router.get("/support/{tid:int}", response_class=HTMLResponse)
def page_support_detail(tid: int, request: Request, user: Annotated[JWTPayload, _USER]):
    return _render_support(request, user, "detail", initial_tid=tid)


# ── Serve uploaded images (prefix /api/support/uploads/ để KHÔNG đụng
# /api/uploads/* của app host — baogia/marketing/... đã có route riêng cho
# lead-images, quote_items, hồ sơ, v.v.)

@router.get("/api/support/uploads/{scope}/{fname}")
def serve_upload(
    scope: str, fname: str,
    user: Annotated[JWTPayload, _USER],
):
    """Serve ảnh ticket. Access: raiser hoặc CN.

    scope pattern: `ticket_{id}` — extract id để check quyền.
    """
    p = resolve_path("support", scope, fname)
    if not p:
        raise HTTPException(404, "File not found")
    # Access check
    if scope.startswith("ticket_"):
        try:
            tid = int(scope.split("_", 1)[1])
        except ValueError:
            raise HTTPException(400, "Invalid scope")
        # Cheap ownership check
        # (Không muốn deps cả DB session ở đây; check bằng raw select nhẹ)
        from shared.db import SessionLocal
        with SessionLocal() as db:
            row = db.execute(
                sql_text("SELECT nguoi_bao FROM congnghe.cn_tickets WHERE id = :id"),
                {"id": tid},
            ).first()
            if not row:
                raise HTTPException(404, "Ticket not found")
            if row[0] != user.username and not _is_cn(user):
                raise HTTPException(403, "Không có quyền xem ảnh này")
    return FileResponse(str(p))
