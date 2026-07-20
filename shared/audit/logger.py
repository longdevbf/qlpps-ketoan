"""Audit log writer — fail-soft (không throw nếu DB down).

Mỗi CRUD endpoint gọi `log_action(db, ...)` sau khi commit thành công.
"""
import logging
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from shared.models import AuditLog
from shared.auth.jwt import JWTPayload


_log = logging.getLogger("audit")


def log_action(
    db: Session,
    app: str,
    action: str,
    user: Optional[JWTPayload] = None,
    resource: Optional[str] = None,
    request: Optional[Request] = None,
    payload: Optional[dict] = None,
    status: str = "ok",
) -> None:
    try:
        entry = AuditLog(
            app=app,
            user_id=user.sub if user else None,
            username=user.username if user else None,
            action=action,
            resource=resource,
            ip=_get_ip(request) if request else None,
            ua=request.headers.get("user-agent") if request else None,
            payload=payload,
            status=status,
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        _log.warning("audit log write failed: %s", e)
        db.rollback()


def log_request(
    db: Session,
    app: str,
    request: Request,
    user: Optional[JWTPayload] = None,
    status: str = "ok",
) -> None:
    """Convenience wrapper — log HTTP request."""
    log_action(
        db,
        app=app,
        action=f"{request.method.lower()}_{request.url.path}",
        user=user,
        resource=str(request.url.path),
        request=request,
        status=status,
    )


def _get_ip(request: Request) -> Optional[str]:
    # Behind nginx: prefer X-Forwarded-For
    from shared.utils import safe_ip
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return safe_ip(fwd)
    return safe_ip(request.client.host if request.client else None)
