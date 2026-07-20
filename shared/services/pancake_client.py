"""Pancake.vn (pages.fm) Public API client — async wrappers cho polling/send.

Khác với `marketing/app/services/pancake.py` (focus aggregate daily stat),
client này dùng cho:
    - Polling worker baogia: list conv updated since last_poll_at
    - Module Chat Zalo: get msg list, send reply

Endpoints (base = https://pages.fm/api/public_api/v1):
    GET  /pages/{pid}/conversations               — list conv (paginated)
    GET  /pages/{pid}/conversations/{cid}/messages — list msg trong 1 conv
    POST /pages/{pid}/conversations/{cid}/messages — gửi reply (action='reply_inbox')

Mọi func fail-soft → trả tuple (data, error) thay vì raise.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

PANCAKE_BASE = "https://pages.fm/api/public_api/v1"
DEFAULT_TIMEOUT = 25.0


async def list_conversations(
    page_id: str,
    access_token: str,
    *,
    since: int,
    until: int,
    page_size: int = 100,
    page_number: int = 1,
) -> tuple[Optional[list[dict]], Optional[str]]:
    """GET /pages/{pid}/conversations.

    since/until là Unix timestamp (int). Pancake filter theo `inserted_at` của
    conv — cho polling, gửi window rộng (since = last_poll_at - 1 day) để bắt
    KH cũ chat lại.

    Trả (list_conversations, error). Mỗi conv là dict raw từ Pancake.
    """
    url = f"{PANCAKE_BASE}/pages/{page_id}/conversations"
    params: dict[str, Any] = {
        "access_token": access_token,
        "since": since,
        "until": until,
        "page_size": page_size,
        "page_number": page_number,
    }
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as cli:
            r = await cli.get(url, params=params)
    except Exception as e:
        return None, f"Network: {e}"

    if r.status_code in (401, 403):
        return None, f"Token expired (HTTP {r.status_code})"
    try:
        data = r.json()
    except Exception:
        return None, f"Non-JSON response (HTTP {r.status_code})"
    if r.status_code >= 400 or data.get("success") is False:
        return None, data.get("message") or f"HTTP {r.status_code}"

    convs = data.get("conversations") or data.get("data") or []
    return convs, None


async def list_messages(
    page_id: str,
    conv_id: str,
    access_token: str,
    *,
    page_size: int = 100,
    page_number: int = 1,
) -> tuple[Optional[list[dict]], Optional[str]]:
    """GET /pages/{pid}/conversations/{cid}/messages.

    Pancake trả mảng msg theo thứ tự time DESC (mới → cũ). page_size=100 là
    tối đa cho 1 lần gọi.
    """
    url = f"{PANCAKE_BASE}/pages/{page_id}/conversations/{conv_id}/messages"
    params = {
        "access_token": access_token,
        "page_size": page_size,
        "page_number": page_number,
    }
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as cli:
            r = await cli.get(url, params=params)
    except Exception as e:
        return None, f"Network: {e}"

    if r.status_code in (401, 403):
        return None, f"Token expired (HTTP {r.status_code})"
    try:
        data = r.json()
    except Exception:
        return None, f"Non-JSON response (HTTP {r.status_code})"
    if r.status_code >= 400 or data.get("success") is False:
        return None, data.get("message") or f"HTTP {r.status_code}"

    return (data.get("messages") or data.get("data") or []), None


async def list_messages_with_meta(
    page_id: str,
    conv_id: str,
    access_token: str,
    *,
    page_size: int = 50,
    page_number: int = 1,
) -> tuple[Optional[dict], Optional[str]]:
    """Như list_messages nhưng trả FULL response dict.

    Anh Quang 2026-06-15 — Pancake `/messages` endpoint trả metadata conv
    kèm messages: birthday, gender, conv_from (profile KH), etc.
    Dùng cho job sync customer profile.
    """
    url = f"{PANCAKE_BASE}/pages/{page_id}/conversations/{conv_id}/messages"
    params = {
        "access_token": access_token,
        "page_size": page_size,
        "page_number": page_number,
    }
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as cli:
            r = await cli.get(url, params=params)
    except Exception as e:
        return None, f"Network: {e}"
    if r.status_code in (401, 403):
        return None, f"Token expired (HTTP {r.status_code})"
    try:
        data = r.json()
    except Exception:
        return None, f"Non-JSON response (HTTP {r.status_code})"
    if r.status_code >= 400 or data.get("success") is False:
        return None, data.get("message") or f"HTTP {r.status_code}"
    return data, None


async def send_message(
    page_id: str,
    conv_id: str,
    access_token: str,
    *,
    text: str,
) -> tuple[Optional[dict], Optional[str]]:
    """POST /pages/{pid}/conversations/{cid}/messages với action=reply_inbox.

    Trả (response_body, error).
    """
    if not text or not text.strip():
        return None, "Nội dung rỗng"
    url = f"{PANCAKE_BASE}/pages/{page_id}/conversations/{conv_id}/messages"
    params = {"access_token": access_token}
    body = {"action": "reply_inbox", "message": text}
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as cli:
            r = await cli.post(url, params=params, json=body)
    except Exception as e:
        return None, f"Network: {e}"

    if r.status_code in (401, 403):
        return None, f"Token expired (HTTP {r.status_code})"
    try:
        data = r.json()
    except Exception:
        return None, f"Non-JSON response (HTTP {r.status_code})"
    if r.status_code >= 400 or data.get("success") is False:
        return None, data.get("message") or f"HTTP {r.status_code}"

    return data, None


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """Chuẩn hoá SĐT VN về dạng 0XXXXXXXXX để match `baogia.customers.sdt`.

    Pancake trả raw có thể: '+84909123456', '84909123456', '0909.123.456', etc.
    Chuẩn hoá: chỉ giữ digit, normalize prefix 84 → 0.
    """
    if not raw:
        return None
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if not digits:
        return None
    # Strip leading 84 country code
    if digits.startswith("84") and len(digits) >= 11:
        digits = "0" + digits[2:]
    if not digits.startswith("0") and len(digits) >= 9:
        digits = "0" + digits
    if len(digits) < 9 or len(digits) > 12:
        return None
    return digits
