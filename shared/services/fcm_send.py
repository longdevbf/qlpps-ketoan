"""shared.services.fcm_send — Lightweight FCM HTTP v1 sender.

Khong dung firebase-admin (~50MB) — viet thuan pyjwt + requests (deps san co).

OAuth2 access token cached in-process (1h TTL).

Config: env var FCM_SA_JSON_B64 chua service account JSON da base64-encode.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import Optional

import jwt as pyjwt
import requests

log = logging.getLogger(__name__)

_TOKEN_CACHE = {"token": None, "exp": 0}
_SA_CACHE = None


def _load_sa() -> Optional[dict]:
    global _SA_CACHE
    if _SA_CACHE is not None:
        return _SA_CACHE or None
    raw_b64 = os.environ.get("FCM_SA_JSON_B64", "").strip()
    if not raw_b64:
        log.warning("FCM_SA_JSON_B64 not set — FCM disabled, mobile push WILL FAIL")
        _SA_CACHE = {}
        return None
    try:
        raw = base64.b64decode(raw_b64).decode("utf-8")
        _SA_CACHE = json.loads(raw)
        return _SA_CACHE
    except Exception as e:
        log.warning("FCM service account decode failed: %s", e)
        _SA_CACHE = {}
        return None


def _get_access_token() -> Optional[str]:
    global _TOKEN_CACHE
    now = int(time.time())
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["exp"] > now + 60:
        return _TOKEN_CACHE["token"]
    sa = _load_sa()
    if not sa:
        return None
    payload = {
        "iss": sa["client_email"],
        "scope": "https://www.googleapis.com/auth/firebase.messaging",
        "aud": sa["token_uri"],
        "iat": now,
        "exp": now + 3600,
    }
    try:
        assertion = pyjwt.encode(payload, sa["private_key"], algorithm="RS256")
    except Exception as e:
        log.warning("FCM SA jwt encode failed: %s", e)
        return None
    try:
        r = requests.post(sa["token_uri"], data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }, timeout=10)
    except Exception as e:
        log.warning("FCM OAuth2 request failed: %s", e)
        return None
    if not r.ok:
        log.warning("FCM OAuth2 returned %s: %s", r.status_code, r.text[:200])
        return None
    body = r.json()
    tok = body.get("access_token")
    if not tok:
        return None
    _TOKEN_CACHE["token"] = tok
    _TOKEN_CACHE["exp"] = now + int(body.get("expires_in", 3600)) - 60
    return tok


# FCM HTTP v1 reserved data payload keys (silently fail with 400 if present)
_FCM_RESERVED_KEYS = {
    "from", "notification", "message_type", "collapse_key", "priority",
    "time_to_live", "delay_while_idle", "on_idle", "dry_run",
}


def send_data_message(fcm_token: str, data: dict, ttl_seconds: int = 60) -> tuple[bool, Optional[int]]:
    """Gui data message uu tien cao toi 1 device.

    Returns (ok, http_status). Khi http=404 hoac code=UNREGISTERED, caller nen
    mark device inactive trong DB.
    """
    sa = _load_sa()
    if not sa:
        return False, None
    access = _get_access_token()
    if not access:
        return False, None
    project_id = sa.get("project_id")
    if not project_id:
        return False, None
    url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    # FCM data values must be strings
    norm = {k: str(v) for k, v in (data or {}).items() if v is not None}
    # Sanitize: rename reserved keys to safe prefixed version (FCM rejects 'from' etc.)
    for rk in list(norm.keys()):
        if rk in _FCM_RESERVED_KEYS or rk.startswith("google") or rk.startswith("gcm."):
            norm["x_" + rk] = norm.pop(rk)
            log.info("FCM payload key %s renamed → x_%s", rk, rk)
    msg = {
        "message": {
            "token": fcm_token,
            "data": norm,
            "android": {
                "priority": "HIGH",
                "ttl": f"{ttl_seconds}s",
                # khong dung notification block — de mobile FCM service tu render
                # full-screen activity (avoid double-notification).
            },
        }
    }
    try:
        r = requests.post(url, json=msg, headers={
            "Authorization": "Bearer " + access,
            "Content-Type": "application/json",
        }, timeout=10)
    except Exception as e:
        log.warning("FCM send exception: %s", e)
        return False, None
    if r.ok:
        return True, r.status_code
    log.info("FCM send non-ok %s: %s", r.status_code, r.text[:300])
    # Hint caller to inactive token
    return False, r.status_code


def fan_out_call(target_username: str, payload: dict, ttl_seconds: int = 60) -> int:
    """Gui FCM cho all device cua user. Return so device gui thanh cong.

    payload should include: call_id, from, from_name, media, room_id, kind.
    ttl_seconds=15 cho call_cancel (cancel push expire nhanh, tranh push ma).
    """
    from shared.db import SessionLocal
    from sqlalchemy import select, update
    from shared.models import MobileDevice

    sent = 0
    db = SessionLocal()
    try:
        rows = db.execute(
            select(MobileDevice).where(
                MobileDevice.username == target_username,
                MobileDevice.active.is_(True),
            )
        ).scalars().all()
        for d in rows:
            ok, code = send_data_message(d.fcm_token, payload, ttl_seconds=ttl_seconds)
            if ok:
                sent += 1
            elif code in (404, 410):
                # Token chet — deactivate
                db.execute(
                    update(MobileDevice).where(MobileDevice.id == d.id).values(active=False)
                )
        db.commit()
    except Exception as e:
        log.warning("fan_out_call error: %s", e)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()
    log.info("fan_out_call target=%s sent=%d/%d type=%s", target_username, sent, len(rows) if 'rows' in dir() else -1, payload.get("type"))
    return sent
