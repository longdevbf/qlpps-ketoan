"""JWT auth utilities — issue, verify, blacklist.

Auth service issues tokens. Mỗi app downstream import:
    from shared.auth import verify_jwt, current_user
    user = Depends(current_user)
"""
from .jwt import (
    create_access_token,
    create_refresh_token,
    access_ttl_min_for_role,
    decode_token,
    verify_jwt,
    current_user,
    require_role,
    require_app,
    require_ceo,
    JWTPayload,
    force_logout_all,
    clear_force_logout,
    is_token_force_logged_out,
)
from .password import hash_password, verify_password

__all__ = [
    "create_access_token",
    "create_refresh_token",
    "access_ttl_min_for_role",
    "decode_token",
    "verify_jwt",
    "current_user",
    "require_role",
    "require_app",
    "require_ceo",
    "JWTPayload",
    "force_logout_all",
    "clear_force_logout",
    "is_token_force_logged_out",
    "hash_password",
    "verify_password",
]
