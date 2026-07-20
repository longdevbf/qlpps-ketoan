"""Shared Jinja2 helpers — compat shim cho templates port từ V1 Flask.

Sử dụng trong main.py mỗi app:
    from shared.templates import setup_jinja2, user_ctx

    templates = Jinja2Templates(directory=...)
    setup_jinja2(templates)
    app.state.templates = templates

Trong pages.py mỗi app:
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user_ctx(user),  # thay vì user.model_dump()
    })
"""
import time
from typing import Optional

from fastapi.templating import Jinja2Templates

from shared.auth.jwt import JWTPayload


# username → (ho_ten, phong_ban, email, chuc_vu, expires_at_epoch)
_USER_INFO_CACHE: dict = {}
_CACHE_TTL_SEC = 300.0   # 5 phút


def _lookup_user_info(username: str) -> tuple[str, str, str, str]:
    """Trả `(ho_ten, phong_ban, email, chuc_vu)` cho 1 username.

    Ưu tiên `shared.users.full_name` (auth_service), fallback `hcns.employees`.
    Cache 5 phút để tránh hit DB mỗi pageload. Trả `("", "", "", "")` khi miss.
    """
    if not username:
        return ("", "", "", "")
    now = time.time()
    cached = _USER_INFO_CACHE.get(username)
    # Cache mới có 5 phần tử (ho_ten, phong_ban, email, chuc_vu, exp).
    # Skip cache cũ (4 phần tử) — sẽ tự rebuild lần đầu sau deploy.
    if cached and len(cached) == 5 and cached[4] > now:
        return cached[0], cached[1], cached[2], cached[3]

    ho_ten = ""
    phong_ban = ""
    email = ""
    chuc_vu = ""
    try:
        from shared.db import SessionLocal
        from sqlalchemy import text as _text
        with SessionLocal() as db:
            row = db.execute(_text(
                "SELECT full_name FROM shared.users WHERE username = :u LIMIT 1"
            ), {"u": username}).first()
            if row and row[0]:
                ho_ten = (row[0] or "").strip()
            # Anh Quang 2026-06-08: lấy thêm chuc_vu — user_ctx dùng nó để
            # promote vai_tro='leader' khi chuc_vu='Leader' dù role không phải.
            row2 = db.execute(_text(
                "SELECT ho_ten, phong_ban, email, chuc_vu FROM hcns.employees "
                "WHERE LOWER(username) = LOWER(:u) LIMIT 1"
            ), {"u": username}).first()
            if row2:
                if not ho_ten and row2[0]:
                    ho_ten = (row2[0] or "").strip()
                phong_ban = (row2[1] or "").strip()
                email = (row2[2] or "").strip()
                chuc_vu = (row2[3] or "").strip()
    except Exception:
        pass

    # Cache giữ chuc_vu ở slot 3, expires ở slot 4 (backward-compat: callers cũ
    # đọc cached[3] sẽ chuyển sang đọc tuple length, không return từ cache.)
    _USER_INFO_CACHE[username] = (ho_ten, phong_ban, email, chuc_vu, now + _CACHE_TTL_SEC)  # type: ignore[assignment]
    return (ho_ten, phong_ban, email, chuc_vu)  # type: ignore[return-value]


def setup_jinja2(templates: Jinja2Templates) -> None:
    """Inject Flask-compat helpers vào Jinja2 env."""
    env = templates.env
    # V1 Flask helper — V2 không dùng flash, return empty list cho compat
    env.globals["get_flashed_messages"] = lambda *a, **kw: []
    # url_for KHÔNG wrap — Starlette tự handle qua jinja_pass_arg(request).
    # Templates đã được port `filename=` → `path=` ở Sprint 1.

    # V1 templates dùng test `containing` cho selectattr filter:
    #   {{ list|selectattr('field','containing','substring')|list }}
    env.tests["containing"] = lambda value, sub: sub in (value or "")


def user_ctx(user: Optional[JWTPayload]) -> Optional[dict]:
    """Build user dict context cho Jinja2 — bổ sung field V1 templates expect.

    V1 user object có: ho_ten, email, role, ma_nv, phong_ban, ...
    V2 JWTPayload có: sub, username, role, apps, ...
    → Map cho compatible.

    `ho_ten` được resolve từ `shared.users.full_name` hoặc `hcns.employees.ho_ten`
    qua cache 5 phút (`_lookup_user_info`). Fallback về `username` khi không có
    name nào trong DB (legacy account).
    """
    if user is None:
        return None
    d = user.model_dump()
    username = d.get("username") or ""
    ho_ten, phong_ban, email, chuc_vu = _lookup_user_info(username)
    # Compat aliases — V1 templates dùng các field này
    d["ho_ten"] = ho_ten or username or "U"
    d["full_name"] = ho_ten or username or ""   # alias cho hcns templates
    d["ma_nv"] = username
    d["ten_dang_nhap"] = username              # alias V1 cho chat_widget
    d["phong_ban"] = phong_ban
    d["nhom"] = phong_ban   # alias V1: templates KD dùng user.nhom = phong_ban
    d["email"] = email
    d["chuc_vu"] = chuc_vu
    # Role flags (V1 base.html dùng _is_mgr / _is_ceo / _is_admin)
    role = d.get("role", "")
    d["_is_admin"] = role == "admin"
    d["_is_ceo"] = role == "ceo"
    d["_is_mgr"] = role in ("manager", "admin", "ceo", "assistant_ceo", "kt")
    d["_is_kt"]  = role in ("manager", "admin", "ceo", "assistant_ceo", "kt")
    d["_is_kd"] = role == "kd"
    d["_is_mkt"] = role == "mkt"
    d["_is_mh"] = role == "mh"
    # V1 alias `vai_tro` — templates check user.vai_tro == 'ceo'/'manager'
    # Anh Quang 2026-06-08: promote vai_tro='leader' khi chuc_vu='Leader' dù
    # role là 'kd'/'kinh_doanh' (vd Quang Linh: role=kd, chuc_vu=Leader).
    chuc_vu_low = (chuc_vu or "").lower()
    is_chuc_vu_leader = ("leader" in chuc_vu_low) or ("trưởng" in chuc_vu_low)
    if role in ("ceo", "admin", "assistant_ceo"):
        d["vai_tro"] = "ceo"   # cấp CEO — full quyền (xóa đơn đã lên hệ thống)
    elif role == "manager":
        d["vai_tro"] = "manager"
    elif role == "leader" or is_chuc_vu_leader:
        d["vai_tro"] = "leader"
    elif role == "kinh_doanh" or role == "kd":
        d["vai_tro"] = "nhan_vien"
    else:
        d["vai_tro"] = role or "nhan_vien"
    return d
