"""Zalo OA config — đọc/ghi creds + token + template + auto_send vào shared.app_config.

4 row trong table (app='zalo_oa'):
    'credentials'   → {app_id, secret_key, oa_id, redirect_url}
    'token'         → {access_token, refresh_token, expires_at, refreshed_at}
    'templates'     → {welcome_lead: template_id, ...} + default_template_id + sample params
    'auto_send'     → {enabled: bool, on_lead_new: bool, updated_by, updated_at}

Anh nhập creds + template_id qua admin UI /marketing/zalo-oa.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.models import AppConfig


_APP = "zalo_oa"


# 6 template keys chuẩn cho Papasan — marketing chủ động gán template_id Zalo đã duyệt vào.
# Mỗi key đi kèm gợi ý params + nhãn UI + màu sắc.
TEMPLATE_KEYS: list[dict] = [
    {
        "key": "welcome_lead",
        "label": "CRM Khách Hàng (Lead mới)",
        "icon": "🆕",
        "color": "amber",
        "description": "Gửi ngay khi NV thêm lead mới vào CRM. Dữ liệu từ app Marketing.",
        "suggested_params": [
            "_GIOI_TINH_KHACH_HANG_",
            "_TEN_KHACH_HANG_",
            "_TEN_SAN_PHAM_",
            "_ID_KHACH_HANG_",
        ],
        "auto_event": "on_lead_new",
        "zalo_template_id": "531454",
    },
    {
        "key": "quote_approved",
        "label": "Xác nhận hóa đơn mua hàng",
        "icon": "✅",
        "color": "green",
        "description": "Khi manager KD duyệt báo giá → gửi xác nhận đơn hàng cho KH. Dữ liệu từ app Báo Giá.",
        "suggested_params": [
            "_TEN_KHACH_HANG_",
            "_ID_DON_HANG_",
            "_CHIET_KHAU_",
            "_NHAN_VIEN_BAN_HANG_",
            "_TIEN_DAT_COC_",
            "_TONG_TIEN_",
            "_NGAY_MUA_",
        ],
        "auto_event": "on_quote_approved",
        "zalo_template_id": "530952",
    },
    {
        "key": "delivered",
        "label": "Giao hàng thành công",
        "icon": "📦",
        "color": "purple",
        "description": "Khi kế toán đánh dấu đơn Đã xong → cảm ơn KH. Dữ liệu từ app Kế Toán.",
        "suggested_params": [
            "_TEN_KHACH_HANG_",
            "_ID_DON_HANG_",
            "_CHIET_KHAU_",
            "_TONG_TIEN_",
            "_TRANG_THAI_DON_HANG_",
        ],
        "auto_event": "on_delivered",
        "zalo_template_id": "530507",
    },
    {
        "key": "promotion",
        "label": "Gửi khuyến mãi",
        "icon": "🎁",
        "color": "rose",
        "description": "Gửi tay khi có chương trình KM mới (chọn KH).",
        "suggested_params": ["_TEN_KHACH_HANG_", "_NOI_DUNG_KM_"],
        "auto_event": None,
    },
    {
        "key": "holiday",
        "label": "Tin ngày lễ",
        "icon": "🎊",
        "color": "cyan",
        "description": "Chúc mừng dịp lễ (Tết, 8/3, 20/10, sinh nhật...).",
        "suggested_params": ["_TEN_KHACH_HANG_", "_NGAY_LE_"],
        "auto_event": None,
    },
    {
        "key": "cskh_followup",
        "label": "Đánh giá trải nghiệm",
        "icon": "💌",
        "color": "blue",
        "description": "Xin đánh giá sau khi KH nhận hàng. Dữ liệu từ app Kế Toán.",
        "suggested_params": [
            "_TEN_KHACH_HANG_",
            "_ID_DON_HANG_",
        ],
        "auto_event": "on_followup",
        "zalo_template_id": "530518",
    },
]


def template_meta(key: str) -> Optional[dict]:
    """Lấy metadata của template key."""
    for t in TEMPLATE_KEYS:
        if t["key"] == key:
            return t
    return None


def _get(db: Session, key: str) -> Optional[dict]:
    row = db.execute(
        select(AppConfig).where(AppConfig.app == _APP, AppConfig.key == key)
    ).scalar_one_or_none()
    return row.value if row else None


def _set(db: Session, key: str, value: dict, user_id: Optional[int] = None) -> None:
    row = db.execute(
        select(AppConfig).where(AppConfig.app == _APP, AppConfig.key == key)
    ).scalar_one_or_none()
    if row is None:
        row = AppConfig(app=_APP, key=key, value=value, updated_by=user_id)
        db.add(row)
    else:
        row.value = value
        if user_id is not None:
            row.updated_by = user_id
    db.commit()


# ── Credentials ─────────────────────────────────────────────────────────────
def load_creds(db: Session) -> dict:
    """{app_id, secret_key, oa_id, redirect_url} hoặc empty dict."""
    return _get(db, "credentials") or {}


def save_creds(
    db: Session,
    *,
    app_id: str,
    secret_key: str,
    oa_id: Optional[str] = None,
    redirect_url: Optional[str] = None,
    user_id: Optional[int] = None,
) -> None:
    cur = load_creds(db)
    if app_id and app_id.strip():
        cur["app_id"] = str(app_id).strip()
    # CHỈ update secret_key nếu non-empty — tránh wipe khi user save với ô trống.
    if secret_key and secret_key.strip():
        cur["secret_key"] = str(secret_key).strip()
    if oa_id is not None:
        cur["oa_id"] = str(oa_id).strip()
    if redirect_url is not None:
        cur["redirect_url"] = str(redirect_url).strip()
    _set(db, "credentials", cur, user_id)


def is_configured(db: Session) -> bool:
    c = load_creds(db)
    return bool(c.get("app_id") and c.get("secret_key"))


# ── Token ────────────────────────────────────────────────────────────────────
def load_token(db: Session) -> dict:
    return _get(db, "token") or {}


def save_token(
    db: Session,
    *,
    access_token: str,
    refresh_token: Optional[str] = None,
    expires_in: Optional[int] = None,  # seconds (Zalo trả 90060s ≈ 25h)
    user_id: Optional[int] = None,
    is_fresh_oauth: bool = False,  # True nếu vừa OAuth (không phải refresh)
) -> None:
    cur = load_token(db)
    cur["access_token"] = str(access_token).strip()
    if refresh_token:
        cur["refresh_token"] = str(refresh_token).strip()
    cur["refreshed_at"] = datetime.now(timezone.utc).isoformat()
    if expires_in is not None:
        exp = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        cur["expires_at"] = exp.isoformat()
    # Reset fail counter mỗi lần save thành công
    cur["refresh_fail_count"] = 0
    # Track tuổi refresh_token gốc — set khi OAuth lần đầu, KHÔNG đổi khi refresh
    if is_fresh_oauth or "refresh_token_issued_at" not in cur:
        cur["refresh_token_issued_at"] = datetime.now(timezone.utc).isoformat()
    _set(db, "token", cur, user_id)


def increment_refresh_fail(db: Session) -> int:
    """Tăng fail counter + trả số lần fail liên tiếp."""
    cur = load_token(db)
    cur["refresh_fail_count"] = int(cur.get("refresh_fail_count") or 0) + 1
    cur["last_refresh_fail_at"] = datetime.now(timezone.utc).isoformat()
    _set(db, "token", cur)
    return cur["refresh_fail_count"]


def has_valid_token(db: Session, *, safety_margin_min: int = 5) -> bool:
    """Token còn dùng được ít nhất `safety_margin_min` phút nữa.

    Zalo User Access Token V4 chỉ sống 1h → safety_margin 5 phút là hợp lý.
    Refresh_token sống ~3 tháng → khi nó hết hạn anh phải re-OAuth thủ công.
    """
    t = load_token(db)
    if not t.get("access_token"):
        return False
    exp = t.get("expires_at")
    if not exp:
        return True  # legacy: chưa lưu expires → giả định còn
    try:
        dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        return dt > datetime.now(timezone.utc) + timedelta(minutes=safety_margin_min)
    except Exception:
        return True


# ── Templates ────────────────────────────────────────────────────────────────
def load_template_config(db: Session) -> dict:
    """Trả config templates ZNS.

    Format:
        {
            "templates": {
                "welcome_lead": {"id": "12345", "params_schema": ["ho_ten", "mkt_phu_trach"]},
                "quote_approved": {"id": "67890", "params_schema": ["ho_ten", "quote_number"]},
                ...
            },
            "default_welcome_lead": "12345"
        }
    """
    cur = _get(db, "templates") or {}
    cur.setdefault("templates", {})
    return cur


def save_template_config(
    db: Session,
    *,
    key: str,                  # 'welcome_lead' | 'quote_approved' | ...
    template_id: str,
    params_schema: Optional[list[str]] = None,
    description: Optional[str] = None,
    user_id: Optional[int] = None,
) -> None:
    cur = load_template_config(db)
    cur["templates"][key] = {
        "id": str(template_id).strip(),
        "params_schema": params_schema or [],
        "description": description or "",
    }
    _set(db, "templates", cur, user_id)


def get_template_id(db: Session, key: str) -> Optional[str]:
    cur = load_template_config(db)
    t = (cur.get("templates") or {}).get(key) or {}
    tid = t.get("id")
    return str(tid).strip() if tid else None


# ── Auto-send toggle ─────────────────────────────────────────────────────────
def load_auto_send(db: Session) -> dict:
    cur = _get(db, "auto_send") or {}
    cur.setdefault("enabled", False)
    # đảm bảo tất cả auto_event keys của TEMPLATE_KEYS đều có entry (default False)
    for t in TEMPLATE_KEYS:
        ev = t.get("auto_event")
        if ev and ev not in cur:
            cur[ev] = False
    return cur


def is_auto_send_enabled(db: Session, event: str = "on_lead_new") -> bool:
    cfg = load_auto_send(db)
    return bool(cfg.get("enabled")) and bool(cfg.get(event))


def set_auto_send(
    db: Session,
    *,
    enabled: Optional[bool] = None,
    flags: Optional[dict[str, bool]] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
) -> None:
    """Update auto_send config.

    `flags` là dict {event_name: bool} — vd {"on_lead_new": True, "on_delivered": False}.
    Chỉ key có trong flags mới được cập nhật.
    """
    cur = load_auto_send(db)
    if enabled is not None:
        cur["enabled"] = bool(enabled)
    if flags:
        for k, v in flags.items():
            if k and k.startswith("on_"):
                cur[k] = bool(v)
    cur["updated_by"] = username or ""
    cur["updated_at"] = datetime.now(timezone.utc).isoformat()
    _set(db, "auto_send", cur, user_id)
