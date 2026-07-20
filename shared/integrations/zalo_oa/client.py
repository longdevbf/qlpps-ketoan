"""Zalo ZNS HTTP client + phone normalization.

API doc: https://developers.zalo.me/docs/api/official-account-api/zns/
Endpoint: POST https://business.openapi.zalo.me/message/template
Headers:  access_token: <OA access_token>
Body:     {phone, template_id, template_data, tracking_id?}
Response: {error: 0, message: "Success", data: {msg_id, sent_time, sent_quota, remaining_quota}}
          error != 0 → message chi tiết. -118 = phone không nhận được; -132 = template chưa duyệt; v.v.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

ZNS_ENDPOINT = "https://business.openapi.zalo.me/message/template"
OAUTH_ENDPOINT = "https://oauth.zaloapp.com/v4/oa/access_token"

_PHONE_DIGIT_RE = re.compile(r"\D+")


def normalize_vn_phone(raw: str) -> Optional[str]:
    """SĐT VN → format Zalo: '84xxxxxxxxx' (10 số sau code, không có dấu +).

    - '0912345678'   → '84912345678'
    - '+84912345678' → '84912345678'
    - '84 912 345 678' → '84912345678'
    - rác / không phải SĐT VN → None
    """
    if not raw:
        return None
    digits = _PHONE_DIGIT_RE.sub("", str(raw))
    if not digits:
        return None
    if digits.startswith("84"):
        if len(digits) == 11:                  # 84 + 9 digit
            return digits
        if len(digits) == 12 and digits[2] == "0":  # 840xx... legacy
            return "84" + digits[3:]
    if digits.startswith("0"):
        if len(digits) == 10:                  # 0xxxxxxxxx
            return "84" + digits[1:]
        if len(digits) == 11:                  # 0xxxxxxxxxx (mạng cũ 11 số)
            return "84" + digits[1:]
    # SĐT thuần 9 số (xxxxxxxxx)
    if len(digits) == 9:
        return "84" + digits
    return None


def send_zns_message(
    *,
    access_token: str,
    phone: str,
    template_id: str,
    template_data: dict[str, Any],
    tracking_id: Optional[str] = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Gọi ZNS API. KHÔNG fail-soft — caller chịu trách nhiệm try/except.

    Returns full Zalo response: {error, message, data?}
    """
    if not access_token:
        raise ValueError("Missing access_token")
    if not phone:
        raise ValueError("Missing phone (E.164 vd 84912345678)")
    if not template_id:
        raise ValueError("Missing template_id (Zalo Cloud đã duyệt)")

    # Zalo expect template_data string values
    td_str = {str(k): ("" if v is None else str(v)) for k, v in (template_data or {}).items()}

    body = {
        "phone": phone,
        "template_id": str(template_id),
        "template_data": td_str,
    }
    if tracking_id:
        body["tracking_id"] = str(tracking_id)[:64]

    logger.info("[ZNS] send phone=%s template=%s tracking=%s", phone, template_id, tracking_id)
    try:
        with httpx.Client(timeout=timeout) as cli:
            r = cli.post(
                ZNS_ENDPOINT,
                headers={"access_token": access_token, "Content-Type": "application/json"},
                json=body,
            )
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        logger.warning("[ZNS] HTTP fail phone=%s: %s", phone, e)
        return {"error": -999, "message": f"HTTP error: {e}", "_http_fail": True}

    logger.info("[ZNS] resp phone=%s error=%s msg=%s", phone, data.get("error"), data.get("message"))
    return data


def list_templates_from_zalo(
    *,
    access_token: str,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Fetch list templates đã tạo trên Zalo của OA này.

    GET https://business.openapi.zalo.me/template/all
    Headers: access_token
    Response: {data: [{templateId, templateName, status, createdTime, ...}], ...}
    """
    if not access_token:
        return {"error": -1, "message": "missing access_token", "data": []}
    try:
        with httpx.Client(timeout=timeout) as cli:
            r = cli.get(
                "https://business.openapi.zalo.me/template/all",
                headers={"access_token": access_token},
                params={"offset": 0, "limit": 100, "status": -1},
            )
        try:
            return r.json()
        except Exception:
            return {"error": -2, "message": "non-JSON response", "raw": r.text[:500]}
    except httpx.HTTPError as e:
        return {"error": -999, "message": f"HTTP error: {e}", "data": []}


def get_template_info(
    *,
    access_token: str,
    template_id: str,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Lấy chi tiết template (content, params, status)."""
    if not access_token or not template_id:
        return {"error": -1, "message": "missing params"}
    try:
        with httpx.Client(timeout=timeout) as cli:
            r = cli.get(
                "https://business.openapi.zalo.me/template/info",
                headers={"access_token": access_token},
                params={"template_id": template_id},
            )
        try:
            return r.json()
        except Exception:
            return {"error": -2, "raw": r.text[:500]}
    except httpx.HTTPError as e:
        return {"error": -999, "message": f"HTTP error: {e}"}


def refresh_oauth_token(
    *,
    app_id: str,
    secret_key: str,
    refresh_token: str,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """OAuth refresh — Zalo trả {access_token, refresh_token, expires_in}.

    ZNS BẮT BUỘC OA access_token → chỉ refresh qua /v4/oa/access_token.
    (User /v4/access_token sẽ trả User token, ZNS fail -125/-124.)
    """
    if not (app_id and secret_key and refresh_token):
        raise ValueError("Missing app_id/secret_key/refresh_token")
    headers = {
        "secret_key": secret_key,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = {
        "app_id": app_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    endpoints = [
        "https://oauth.zaloapp.com/v4/oa/access_token",
    ]
    import json as _json
    attempts = []
    for ep in endpoints:
        try:
            with httpx.Client(timeout=timeout) as cli:
                r = cli.post(ep, headers=headers, data=payload)
                # Force parse JSON regardless of content-type (Zalo trả text/html)
                try:
                    data = _json.loads(r.text)
                except Exception:
                    data = {"raw": r.text, "status": r.status_code}
            attempts.append({"endpoint": ep, "status": r.status_code, "data": data})
            if data.get("access_token"):
                return data
        except httpx.HTTPError as e:
            logger.warning("[ZNS oauth refresh] %s fail: %s", ep, e)
            attempts.append({"endpoint": ep, "exception": str(e)})
    # Return last error with debug
    return {"error": -1, "message": "all endpoints failed", "attempts": attempts}
