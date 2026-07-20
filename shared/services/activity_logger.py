"""Helper log NV activity + Mai interaction — fail-soft, không raise.

Pattern usage trong router POST endpoints:

    from shared.services.activity_logger import log_activity
    ...
    db.commit()
    log_activity(db, user.username, action='po_create', app='muahang',
                 ref_type='purchase_order', ref_id=po.id,
                 metadata={'amount': float(po.total)})

Pattern cho Mai interaction (gọi trong chat_hook sau khi Mai trả lời):

    from shared.services.activity_logger import log_mai_interaction
    log_mai_interaction(db, username, room_id=room_id, ...)
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def log_activity(
    db: Session,
    username: str,
    *,
    action: str,
    app: str | None = None,
    ref_type: str | None = None,
    ref_id: Any = None,
    metadata: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> None:
    """INSERT 1 row vào shared.nv_activity. Fail-soft.

    Caller chịu trách nhiệm db.commit() (function dùng session hiện tại).
    Nếu DB lỗi → log warning, swallow → không ảnh hưởng request chính.
    """
    if not username or not action:
        return
    try:
        db.execute(
            text(
                """
                INSERT INTO shared.nv_activity
                    (username, action, app, ref_type, ref_id, metadata, duration_ms)
                VALUES
                    (:u, :a, :app, :rt, :ri, CAST(:m AS jsonb), :dur)
                """
            ),
            {
                "u": username, "a": action, "app": app,
                "rt": ref_type, "ri": str(ref_id) if ref_id is not None else None,
                "m": _json_dump(metadata),
                "dur": duration_ms,
            },
        )
        db.commit()
    except Exception as e:
        logger.warning("log_activity %s/%s fail: %s", username, action, e)
        try:
            db.rollback()
        except Exception:
            pass


def log_mai_interaction(
    db: Session,
    username: str,
    *,
    room_id: int | None = None,
    chat_message_id: int | None = None,
    category: str | None = None,
    intent: str | None = None,
    tools_used: list[str] | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_usd: float | None = None,
    outcome: str | None = None,
    duration_ms: int | None = None,
    satisfaction: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """INSERT 1 row vào shared.mai_interaction. Fail-soft."""
    if not username:
        return
    try:
        db.execute(
            text(
                """
                INSERT INTO shared.mai_interaction
                    (username, room_id, chat_message_id, category, intent,
                     tools_used, tokens_in, tokens_out, cost_usd, outcome,
                     duration_ms, satisfaction, metadata)
                VALUES
                    (:u, :rid, :mid, :cat, :intent, CAST(:tools AS text[]),
                     :ti, :to, :cost, :oc, :dur, :sat, CAST(:meta AS jsonb))
                """
            ),
            {
                "u": username, "rid": room_id, "mid": chat_message_id,
                "cat": category, "intent": intent,
                "tools": tools_used or [],
                "ti": tokens_in, "to": tokens_out, "cost": cost_usd,
                "oc": outcome, "dur": duration_ms, "sat": satisfaction,
                "meta": _json_dump(metadata),
            },
        )
        db.commit()
    except Exception as e:
        logger.warning("log_mai_interaction %s fail: %s", username, e)
        try:
            db.rollback()
        except Exception:
            pass


def _json_dump(d: dict[str, Any] | None) -> str | None:
    if d is None:
        return None
    try:
        import json
        return json.dumps(d, ensure_ascii=False, default=str)
    except Exception:
        return None
