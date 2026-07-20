"""Audit log — append-only mọi CRUD 3 app, write vào shared.audit_log table.

Usage:
    from shared.audit import log_action

    log_action(
        db, app="baogia", user=current_user, action="create_quote",
        resource=f"quote:{quote.id}", payload={"customer": "..."}
    )
"""
from .logger import log_action, log_request

__all__ = ["log_action", "log_request"]
