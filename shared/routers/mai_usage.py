"""Mai Usage Analytics API — CEO xem NV đang dùng Mai (AI trợ lý) thế nào.

Endpoints (yêu cầu CEO read):
  GET /overview?period=week                  — tổng câu hỏi, active users, cost, breakdown level
  GET /by-user?period=week&top=10            — top N NV hỏi nhiều nhất (JOIN ho_ten, phong_ban)
  GET /by-department?period=week             — gom theo phòng ban
  GET /by-day?period=month                   — trend timeline số câu/ngày
  GET /messages?username=X&limit=50          — list câu hỏi của 1 NV + reply Mai (rút gọn)

Source data: `shared.ai_chat_message` JOIN `hcns.employees` ON e.username = m.username.
  role='user'      → câu hỏi của NV.
  role='assistant' → reply của Mai (đối ứng theo created_at).

Mounted bởi orchestrator vào CEO main.py với prefix `/api/mai-usage`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.auth import JWTPayload, require_ceo
from shared.db import get_db

router = APIRouter()

_AUTH_READ = Depends(require_ceo(write=False))

# ─── Helpers ─────────────────────────────────────────────────────────────
_VALID_PERIODS = {"today", "week", "month", "all"}


def _period_start(period: str) -> Optional[datetime]:
    """Trả về datetime mốc đầu period (UTC) — None nếu 'all'."""
    p = (period or "week").strip().lower()
    if p not in _VALID_PERIODS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"period không hợp lệ — phải thuộc {sorted(_VALID_PERIODS)}",
        )
    if p == "all":
        return None
    now = datetime.now(timezone.utc)
    if p == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if p == "week":
        return now - timedelta(days=7)
    # month
    return now - timedelta(days=30)


# ─── Schemas ─────────────────────────────────────────────────────────────
class OverviewOut(BaseModel):
    period: str
    date_from: Optional[datetime] = None
    total_questions: int
    total_users: int
    total_cost_usd: float
    avg_questions_per_day: float
    by_level: dict = Field(default_factory=dict, description="brief_level → count")


class ByUserOut(BaseModel):
    username: str
    ho_ten: Optional[str] = None
    phong_ban: Optional[str] = None
    questions: int
    tokens: int
    cost_usd: float
    last_at: Optional[datetime] = None


class ByDepartmentOut(BaseModel):
    phong_ban: str
    so_nv_active: int
    questions: int
    cost_usd: float


class ByDayOut(BaseModel):
    day: date
    questions: int


class MessageOut(BaseModel):
    id: int
    role: str
    content_preview: str
    brief_level: Optional[str] = None
    cost_usd: float
    tokens_in: int
    tokens_out: int
    created_at: datetime
    reply_preview: Optional[str] = None


# ─── Endpoints ───────────────────────────────────────────────────────────
@router.get("/overview", response_model=OverviewOut)
def overview(
    _user: Annotated[JWTPayload, _AUTH_READ],
    db: Annotated[Session, Depends(get_db)],
    period: str = Query("week"),
):
    date_from = _period_start(period)
    params: dict = {}
    where_clauses = ["m.role = 'user'"]
    if date_from is not None:
        where_clauses.append("m.created_at >= :date_from")
        params["date_from"] = date_from
    where_sql = " AND ".join(where_clauses)

    # Totals
    row = db.execute(
        text(f"""
            SELECT
              COUNT(*) AS total_questions,
              COUNT(DISTINCT m.username) AS total_users,
              COALESCE(SUM(m.cost_usd), 0)::float8 AS total_cost
            FROM shared.ai_chat_message m
            WHERE {where_sql}
        """),
        params,
    ).mappings().one()

    total_q = int(row["total_questions"] or 0)
    total_u = int(row["total_users"] or 0)
    total_cost = float(row["total_cost"] or 0.0)

    # By level
    level_rows = db.execute(
        text(f"""
            SELECT COALESCE(NULLIF(m.brief_level, ''), '(none)') AS lvl,
                   COUNT(*) AS cnt
            FROM shared.ai_chat_message m
            WHERE {where_sql}
            GROUP BY lvl
            ORDER BY cnt DESC
        """),
        params,
    ).mappings().all()
    by_level = {r["lvl"]: int(r["cnt"]) for r in level_rows}

    # Avg per day (theo span period)
    if date_from is None:
        # all-time: lấy ngày sớm nhất
        first = db.execute(
            text("SELECT MIN(created_at) AS first_at FROM shared.ai_chat_message WHERE role='user'")
        ).scalar_one_or_none()
        if first is None:
            span_days = 1
        else:
            span_days = max(1, (datetime.now(timezone.utc) - first).days or 1)
    else:
        span_days = max(1, (datetime.now(timezone.utc) - date_from).days or 1)
    avg_per_day = round(total_q / span_days, 2) if span_days else 0.0

    return OverviewOut(
        period=period,
        date_from=date_from,
        total_questions=total_q,
        total_users=total_u,
        total_cost_usd=total_cost,
        avg_questions_per_day=avg_per_day,
        by_level=by_level,
    )


@router.get("/by-user", response_model=List[ByUserOut])
def by_user(
    _user: Annotated[JWTPayload, _AUTH_READ],
    db: Annotated[Session, Depends(get_db)],
    period: str = Query("week"),
    top: int = Query(10, ge=1, le=200),
):
    date_from = _period_start(period)
    params: dict = {"top": top}
    where_clauses = ["m.role = 'user'"]
    if date_from is not None:
        where_clauses.append("m.created_at >= :date_from")
        params["date_from"] = date_from
    where_sql = " AND ".join(where_clauses)

    rows = db.execute(
        text(f"""
            SELECT
              m.username,
              MAX(e.ho_ten)    AS ho_ten,
              MAX(e.phong_ban) AS phong_ban,
              COUNT(*)         AS questions,
              COALESCE(SUM(m.tokens_in + m.tokens_out), 0)::bigint AS tokens,
              COALESCE(SUM(m.cost_usd), 0)::float8 AS cost_usd,
              MAX(m.created_at) AS last_at
            FROM shared.ai_chat_message m
            LEFT JOIN hcns.employees e ON e.username = m.username
            WHERE {where_sql}
            GROUP BY m.username
            ORDER BY questions DESC, last_at DESC NULLS LAST
            LIMIT :top
        """),
        params,
    ).mappings().all()

    return [
        ByUserOut(
            username=r["username"],
            ho_ten=r["ho_ten"],
            phong_ban=r["phong_ban"],
            questions=int(r["questions"] or 0),
            tokens=int(r["tokens"] or 0),
            cost_usd=float(r["cost_usd"] or 0.0),
            last_at=r["last_at"],
        )
        for r in rows
    ]


@router.get("/by-department", response_model=List[ByDepartmentOut])
def by_department(
    _user: Annotated[JWTPayload, _AUTH_READ],
    db: Annotated[Session, Depends(get_db)],
    period: str = Query("week"),
):
    date_from = _period_start(period)
    params: dict = {}
    where_clauses = ["m.role = 'user'"]
    if date_from is not None:
        where_clauses.append("m.created_at >= :date_from")
        params["date_from"] = date_from
    where_sql = " AND ".join(where_clauses)

    rows = db.execute(
        text(f"""
            SELECT
              COALESCE(NULLIF(e.phong_ban, ''), '(Khác)') AS phong_ban,
              COUNT(DISTINCT m.username) AS so_nv_active,
              COUNT(*)                   AS questions,
              COALESCE(SUM(m.cost_usd), 0)::float8 AS cost_usd
            FROM shared.ai_chat_message m
            LEFT JOIN hcns.employees e ON e.username = m.username
            WHERE {where_sql}
            GROUP BY COALESCE(NULLIF(e.phong_ban, ''), '(Khác)')
            ORDER BY questions DESC
        """),
        params,
    ).mappings().all()

    return [
        ByDepartmentOut(
            phong_ban=r["phong_ban"],
            so_nv_active=int(r["so_nv_active"] or 0),
            questions=int(r["questions"] or 0),
            cost_usd=float(r["cost_usd"] or 0.0),
        )
        for r in rows
    ]


@router.get("/by-day", response_model=List[ByDayOut])
def by_day(
    _user: Annotated[JWTPayload, _AUTH_READ],
    db: Annotated[Session, Depends(get_db)],
    period: str = Query("month"),
):
    date_from = _period_start(period)
    params: dict = {}
    where_clauses = ["m.role = 'user'"]
    if date_from is not None:
        where_clauses.append("m.created_at >= :date_from")
        params["date_from"] = date_from
    where_sql = " AND ".join(where_clauses)

    rows = db.execute(
        text(f"""
            SELECT
              DATE(m.created_at) AS day,
              COUNT(*)           AS questions
            FROM shared.ai_chat_message m
            WHERE {where_sql}
            GROUP BY DATE(m.created_at)
            ORDER BY day ASC
        """),
        params,
    ).mappings().all()

    return [ByDayOut(day=r["day"], questions=int(r["questions"] or 0)) for r in rows]


@router.get("/messages", response_model=List[MessageOut])
def messages(
    _user: Annotated[JWTPayload, _AUTH_READ],
    db: Annotated[Session, Depends(get_db)],
    username: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
):
    """List câu hỏi gần đây của 1 NV, kèm reply (rút gọn 200 ký tự) của Mai.

    Reply được pair theo: assistant message đầu tiên của cùng user_id có
    created_at > question.created_at (giả định lưu tuần tự).
    """
    u = (username or "").strip()
    if not u:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "username không được trống")

    # 1) Lấy N câu hỏi mới nhất của user
    q_rows = db.execute(
        text("""
            SELECT id, user_id, role, content, brief_level,
                   COALESCE(cost_usd, 0)::float8 AS cost_usd,
                   COALESCE(tokens_in, 0)  AS tokens_in,
                   COALESCE(tokens_out, 0) AS tokens_out,
                   created_at
            FROM shared.ai_chat_message
            WHERE username = :u AND role = 'user'
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"u": u, "limit": limit},
    ).mappings().all()

    if not q_rows:
        return []

    # 2) Pair với assistant reply tiếp theo của cùng user_id
    out: List[MessageOut] = []
    for r in q_rows:
        reply_row = db.execute(
            text("""
                SELECT content
                FROM shared.ai_chat_message
                WHERE user_id = :uid AND role = 'assistant'
                  AND created_at > :qt
                ORDER BY created_at ASC
                LIMIT 1
            """),
            {"uid": r["user_id"], "qt": r["created_at"]},
        ).scalar_one_or_none()

        content = r["content"] or ""
        preview = content[:200] + ("…" if len(content) > 200 else "")
        rp: Optional[str] = None
        if reply_row:
            rp = reply_row[:200] + ("…" if len(reply_row) > 200 else "")

        out.append(
            MessageOut(
                id=int(r["id"]),
                role=r["role"],
                content_preview=preview,
                brief_level=r["brief_level"],
                cost_usd=float(r["cost_usd"] or 0.0),
                tokens_in=int(r["tokens_in"] or 0),
                tokens_out=int(r["tokens_out"] or 0),
                created_at=r["created_at"],
                reply_preview=rp,
            )
        )
    return out
