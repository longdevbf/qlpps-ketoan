"""Mai Insights — API cho dashboard CEO xem NV xài Mai + hành vi NV.

Endpoints (prefix /api/mai-insights):
  GET /summary?date_from=&date_to=
      → per-NV: # chat, # category breakdown, # action, cost, satisfaction.
  GET /heatmap?date_from=&date_to=
      → matrix user × hour-of-day → count_action (sum chat + activity).
  GET /timeline/{username}?date_from=&date_to=&limit=
      → mọi event của user theo thời gian (mai_interaction + nv_activity merged).
  GET /top-intents?date_from=&date_to=
      → top intent + top action toàn org.

Require CEO/admin/assistant_ceo (require_ceo).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.auth import JWTPayload, require_ceo
from shared.db import get_db


router = APIRouter()
_AUTH = Depends(require_ceo)


def _parse_range(date_from: Optional[date], date_to: Optional[date]) -> tuple[datetime, datetime]:
    today = datetime.now(timezone.utc).date()
    df = date_from or (today - timedelta(days=7))
    dt = date_to or today
    start = datetime.combine(df, datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(dt + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    return start, end


# ── 1. Per-NV summary ──────────────────────────────────────────────────────
@router.get("/summary")
def summary(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
) -> list[dict[str, Any]]:
    start, end = _parse_range(date_from, date_to)
    rows = db.execute(
        text(
            """
            WITH chat AS (
                SELECT username,
                       COUNT(*) AS n_chat,
                       COALESCE(SUM(tokens_in), 0)  AS tin,
                       COALESCE(SUM(tokens_out), 0) AS tout,
                       COALESCE(SUM(cost_usd), 0)::float AS cost,
                       SUM(CASE WHEN category='data_query' THEN 1 ELSE 0 END) AS cat_data,
                       SUM(CASE WHEN category='task_create' THEN 1 ELSE 0 END) AS cat_task,
                       SUM(CASE WHEN category='approval'  THEN 1 ELSE 0 END) AS cat_apv,
                       SUM(CASE WHEN category='casual'    THEN 1 ELSE 0 END) AS cat_casual,
                       SUM(CASE WHEN category='refusal'   THEN 1 ELSE 0 END) AS cat_refusal,
                       SUM(CASE WHEN outcome='error'      THEN 1 ELSE 0 END) AS n_error,
                       MAX(created_at) AS last_chat_at
                FROM shared.mai_interaction
                WHERE created_at >= :s AND created_at < :e
                GROUP BY username
            ),
            act AS (
                SELECT username,
                       COUNT(*) AS n_action,
                       MAX(created_at) AS last_action_at
                FROM shared.nv_activity
                WHERE created_at >= :s AND created_at < :e
                GROUP BY username
            ),
            users AS (
                SELECT username, ho_ten, role, phong_ban FROM hcns.employees
                WHERE COALESCE(trang_thai,'')='Đang làm' AND username IS NOT NULL
                  AND username <> 'mai_ai'
            )
            SELECT u.username, u.ho_ten, u.role, u.phong_ban,
                   COALESCE(c.n_chat, 0)     AS n_chat,
                   COALESCE(c.tin, 0)        AS tokens_in,
                   COALESCE(c.tout, 0)       AS tokens_out,
                   COALESCE(c.cost, 0)       AS cost_usd,
                   COALESCE(c.cat_data, 0)   AS cat_data,
                   COALESCE(c.cat_task, 0)   AS cat_task,
                   COALESCE(c.cat_apv, 0)    AS cat_approval,
                   COALESCE(c.cat_casual, 0) AS cat_casual,
                   COALESCE(c.cat_refusal,0) AS cat_refusal,
                   COALESCE(c.n_error, 0)    AS n_error,
                   COALESCE(a.n_action, 0)   AS n_action,
                   c.last_chat_at, a.last_action_at
            FROM users u
            LEFT JOIN chat c ON c.username = u.username
            LEFT JOIN act  a ON a.username = u.username
            ORDER BY (COALESCE(c.n_chat,0) + COALESCE(a.n_action,0)) DESC, u.ho_ten
            """
        ),
        {"s": start, "e": end},
    ).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        # iso datetimes
        for k in ("last_chat_at", "last_action_at"):
            v = d.get(k)
            if v:
                d[k] = v.isoformat()
        out.append(d)
    return out


# ── 2. Heatmap user × hour ─────────────────────────────────────────────────
@router.get("/heatmap")
def heatmap(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
) -> dict[str, Any]:
    start, end = _parse_range(date_from, date_to)
    rows = db.execute(
        text(
            """
            SELECT username,
                   EXTRACT(HOUR FROM (created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'))::int AS hour,
                   COUNT(*) AS n
            FROM (
                SELECT username, created_at FROM shared.mai_interaction
                WHERE created_at >= :s AND created_at < :e
                UNION ALL
                SELECT username, created_at FROM shared.nv_activity
                WHERE created_at >= :s AND created_at < :e
            ) t
            GROUP BY username, hour
            """
        ),
        {"s": start, "e": end},
    ).all()
    grid: dict[str, dict[int, int]] = {}
    for u, h, n in rows:
        grid.setdefault(u, {})[int(h)] = int(n)
    # Tổng hợp về list flat cho FE dễ render
    users_sorted = sorted(grid.keys(), key=lambda u: -sum(grid[u].values()))
    return {
        "users": users_sorted,
        "matrix": {u: [grid[u].get(h, 0) for h in range(24)] for u in users_sorted},
    }


# ── 3. Timeline per-user ───────────────────────────────────────────────────
@router.get("/timeline/{username}")
def timeline(
    username: str,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(200, le=500),
) -> list[dict[str, Any]]:
    start, end = _parse_range(date_from, date_to)
    rows = db.execute(
        text(
            """
            SELECT 'mai' AS kind, created_at, category AS type, intent AS detail,
                   tools_used::text AS extra, cost_usd::float AS cost,
                   chat_message_id AS ref_id, NULL::text AS app
            FROM shared.mai_interaction
            WHERE username = :u AND created_at >= :s AND created_at < :e
            UNION ALL
            SELECT 'activity' AS kind, created_at, action AS type, ref_type AS detail,
                   metadata::text AS extra, NULL::float AS cost,
                   ref_id, app
            FROM shared.nv_activity
            WHERE username = :u AND created_at >= :s AND created_at < :e
            ORDER BY created_at DESC
            LIMIT :lim
            """
        ),
        {"u": username, "s": start, "e": end, "lim": limit},
    ).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        out.append(d)
    return out


# ── 4. Top intents + top actions ──────────────────────────────────────────
@router.get("/top-intents")
def top_intents(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
) -> dict[str, list[dict[str, Any]]]:
    start, end = _parse_range(date_from, date_to)
    intents = db.execute(
        text(
            """
            SELECT intent, category, COUNT(*) AS n
            FROM shared.mai_interaction
            WHERE created_at >= :s AND created_at < :e AND intent IS NOT NULL
            GROUP BY intent, category
            ORDER BY n DESC LIMIT 15
            """
        ),
        {"s": start, "e": end},
    ).mappings().all()
    actions = db.execute(
        text(
            """
            SELECT action, app, COUNT(*) AS n
            FROM shared.nv_activity
            WHERE created_at >= :s AND created_at < :e
            GROUP BY action, app
            ORDER BY n DESC LIMIT 15
            """
        ),
        {"s": start, "e": end},
    ).mappings().all()
    return {
        "intents": [dict(r) for r in intents],
        "actions": [dict(r) for r in actions],
    }


# ── 5. Activity stream — merge proactive (mai_notified_items) + reactive (mai_interaction) ──
@router.get("/activity-stream")
def activity_stream(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    kind: str = Query("all"),
    username: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
) -> list[dict[str, Any]]:
    start, end = _parse_range(date_from, date_to)
    k = (kind or "all").strip().lower()

    # Quyết định include proactive / reactive + extra WHERE
    include_proactive = k in ("all", "proactive", "auto_approve", "escalate", "daily_brief", "event_t30")
    include_reactive = k in ("all", "reactive", "chat")

    extra_proactive = ""
    if k == "auto_approve":
        extra_proactive = " AND n.decision = 'auto_approve'"
    elif k == "escalate":
        extra_proactive = " AND n.decision = 'escalate'"
    elif k == "daily_brief":
        extra_proactive = " AND n.item_source = 'daily_brief'"
    elif k == "event_t30":
        extra_proactive = " AND n.item_source = 'event_t30'"

    username_clause_p = " AND n.requested_by_username = :uname" if username else ""
    username_clause_r = " AND i.username = :uname" if username else ""

    proactive_sql = f"""
        SELECT
            'proactive'::text                          AS kind,
            COALESCE(n.decision, n.item_source)        AS sub_kind,
            n.notified_at                              AS created_at,
            n.requested_by_username                    AS username,
            e.ho_ten                                   AS ho_ten,
            e.phong_ban                                AS phong_ban,
            n.item_source                              AS source,
            n.item_ref_id                              AS ref_id,
            n.decision                                 AS decision,
            NULL::text                                 AS category,
            NULL::text                                 AS intent,
            NULL::text                                 AS tools_used,
            NULL::text                                 AS outcome,
            NULL::float                                AS cost_usd,
            LEFT(COALESCE(cm.content, ''), 200)        AS content_preview
        FROM shared.mai_notified_items n
        LEFT JOIN hcns.chat_messages cm ON cm.id = n.dm_message_id
        LEFT JOIN hcns.employees     e  ON e.username = n.requested_by_username
        WHERE n.notified_at >= :s AND n.notified_at < :e
          {extra_proactive}
          {username_clause_p}
    """

    reactive_sql = f"""
        SELECT
            'reactive'::text                           AS kind,
            'chat_reply'::text                         AS sub_kind,
            i.created_at                               AS created_at,
            i.username                                 AS username,
            e.ho_ten                                   AS ho_ten,
            e.phong_ban                                AS phong_ban,
            NULL::text                                 AS source,
            NULL::text                                 AS ref_id,
            NULL::text                                 AS decision,
            i.category                                 AS category,
            i.intent                                   AS intent,
            i.tools_used::text                         AS tools_used,
            i.outcome                                  AS outcome,
            i.cost_usd::float                          AS cost_usd,
            LEFT(COALESCE(cm.content, ''), 200)        AS content_preview
        FROM shared.mai_interaction i
        LEFT JOIN hcns.chat_messages cm ON cm.id = i.chat_message_id
        LEFT JOIN hcns.employees     e  ON e.username = i.username
        WHERE i.created_at >= :s AND i.created_at < :e
          {username_clause_r}
    """

    if include_proactive and include_reactive:
        sql = f"""
            SELECT * FROM (
                {proactive_sql}
                UNION ALL
                {reactive_sql}
            ) t
            ORDER BY created_at DESC
            LIMIT :lim
        """
    elif include_proactive:
        sql = f"""
            SELECT * FROM (
                {proactive_sql}
            ) t
            ORDER BY created_at DESC
            LIMIT :lim
        """
    elif include_reactive:
        sql = f"""
            SELECT * FROM (
                {reactive_sql}
            ) t
            ORDER BY created_at DESC
            LIMIT :lim
        """
    else:
        return []

    params: dict[str, Any] = {"s": start, "e": end, "lim": limit}
    if username:
        params["uname"] = username

    rows = db.execute(text(sql), params).mappings().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        # Parse tools_used text → list (best-effort)
        tu = d.get("tools_used")
        if tu and isinstance(tu, str):
            s = tu.strip()
            if s.startswith("{") and s.endswith("}"):
                inner = s[1:-1].strip()
                if inner:
                    d["tools_used"] = [x.strip().strip('"') for x in inner.split(",")]
                else:
                    d["tools_used"] = []
        out.append(d)
    return out


# ── 6. Activity stats — KPI cards header ──────────────────────────────────
@router.get("/activity-stats")
def activity_stats(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, int]:
    row = db.execute(
        text(
            """
            WITH today_range AS (
                SELECT
                    date_trunc('day', (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')) AT TIME ZONE 'Asia/Ho_Chi_Minh' AS s,
                    (date_trunc('day', (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')) + interval '1 day') AT TIME ZONE 'Asia/Ho_Chi_Minh' AS e
            )
            SELECT
                (SELECT COUNT(*) FROM shared.mai_notified_items n, today_range tr
                    WHERE n.notified_at >= tr.s AND n.notified_at < tr.e)                          AS today_dm_count,
                (SELECT COUNT(*) FROM shared.mai_notified_items n, today_range tr
                    WHERE n.notified_at >= tr.s AND n.notified_at < tr.e
                      AND n.decision = 'auto_approve')                                             AS today_auto_approve,
                (SELECT COUNT(*) FROM shared.mai_notified_items n, today_range tr
                    WHERE n.notified_at >= tr.s AND n.notified_at < tr.e
                      AND n.decision = 'escalate')                                                 AS today_escalate,
                (SELECT COUNT(*) FROM shared.mai_interaction i, today_range tr
                    WHERE i.created_at >= tr.s AND i.created_at < tr.e)                            AS today_chat_reply
            """
        )
    ).mappings().first()
    if not row:
        return {
            "today_dm_count": 0,
            "today_auto_approve": 0,
            "today_escalate": 0,
            "today_chat_reply": 0,
        }
    return {
        "today_dm_count": int(row["today_dm_count"] or 0),
        "today_auto_approve": int(row["today_auto_approve"] or 0),
        "today_escalate": int(row["today_escalate"] or 0),
        "today_chat_reply": int(row["today_chat_reply"] or 0),
    }
