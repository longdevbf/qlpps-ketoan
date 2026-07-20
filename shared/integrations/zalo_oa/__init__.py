"""Zalo OA / ZNS integration — chủ động nhắn khách hàng từ OA Papasan.

Module thiết kế ready-to-run: chỉ cần CEO/Admin nhập creds qua admin UI
(/marketing/zalo-oa) + Zalo duyệt template → hook auto fire khi lead mới.

Public API:
    from shared.integrations.zalo_oa import send_zns_for_lead, refresh_token_if_needed
"""
# ruff: noqa: F401
from .worker import (
    send_zns_for_lead,
    send_zns_for_quote,
    refresh_token_if_needed,
    check_refresh_token_age_and_alert,
)
from .client import send_zns_message, normalize_vn_phone
from .config import (
    load_creds, save_creds, is_configured,
    load_token, save_token, has_valid_token,
    load_template_config, save_template_config,
    is_auto_send_enabled, set_auto_send,
    increment_refresh_fail,
)

__all__ = [
    "send_zns_for_lead", "send_zns_for_quote",
    "refresh_token_if_needed", "check_refresh_token_age_and_alert",
    "send_zns_message", "normalize_vn_phone",
    "load_creds", "save_creds", "is_configured",
    "load_token", "save_token", "has_valid_token",
    "load_template_config", "save_template_config",
    "is_auto_send_enabled", "set_auto_send",
    "increment_refresh_fail",
]
