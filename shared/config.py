"""Centralized config loader cho mọi app V2.

Mỗi app FastAPI import `from shared.config import settings` để lấy env vars.
Pydantic v2 Settings tự load `.env` ở root App_V2/.
"""
import logging
import os
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


_ROOT = Path(__file__).resolve().parent.parent  # App_V2/
_logger = logging.getLogger(__name__)

_DEFAULT_JWT_SECRET = "change-me-prod-32-bytes-random"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+psycopg://qlpps:qlpps_dev_pw@localhost:5432/qlpps_dev"
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret_key: str = "change-me-prod-32-bytes-random"
    jwt_alg: str = "HS256"
    jwt_access_ttl_min: int = 43200   # 30 ngày — không tự đăng xuất
    jwt_access_ttl_min_ceo: int = 43200   # 30 ngày — phiên CEO không tự đăng xuất
    jwt_refresh_ttl_days: int = 365   # 1 năm

    # App ports
    auth_host: str = "localhost"   # Docker prod: 'auth' (container name)
    auth_port: int = 8000
    baogia_port: int = 8001
    marketing_port: int = 8002
    muahang_port: int = 8003
    hcns_port: int = 8004
    ketoan_port: int = 8005
    saleadmin_port: int = 8006

    # Storage
    upload_dir: str = "./_storage/uploads"

    # Sentry
    sentry_dsn: str = ""

    # Web Push (VAPID) — để trống thì /api/push/* trả 503, không break app khác
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@qlpps.com"

    # Webhook ingest secrets (Sprint 1-D)
    # Để trống ở dev → bỏ qua HMAC verify cho dễ test bằng cURL.
    # Chỉ verify khi có giá trị (production hoặc khi anh fill vào .env).
    pancake_webhook_secret: str = ""
    zalo_oa_secret: str = ""
    zalo_oa_verify_token: str = ""
    fb_app_secret: str = ""
    fb_verify_token: str = ""

    # Env
    app_env: str = "development"
    log_level: str = "INFO"

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    @property
    def is_prod(self) -> bool:
        return self.app_env == "production"

    def model_post_init(self, __context) -> None:
        """Security check: cấm dùng JWT secret default ở production.

        Production = ENV / ENVIRONMENT / PAPASAN_ENV ∈ {prod, production}
        hoặc app_env (load từ .env) = production.
        """
        env_marker = (
            os.getenv("ENV")
            or os.getenv("ENVIRONMENT")
            or os.getenv("PAPASAN_ENV")
            or self.app_env
            or ""
        ).lower()
        is_production = env_marker in ("prod", "production")
        if self.jwt_secret_key == _DEFAULT_JWT_SECRET:
            if is_production:
                raise RuntimeError(
                    "SECURITY: jwt_secret_key đang dùng default value trong "
                    "production. Set env JWT_SECRET_KEY (>=32 bytes random) "
                    "trước khi deploy."
                )
            # SECURITY: bump severity từ warning → error để CI/log aggregation
            # bắt được sớm khi quên set JWT_SECRET_KEY (dù vẫn cho phép chạy dev).
            _logger.error(
                "SECURITY: jwt_secret_key đang dùng DEFAULT value (dev mode). "
                "Token có thể bị forge. PHẢI set JWT_SECRET_KEY (>=32 bytes random) "
                "trong .env trước khi deploy production hoặc share env qua mạng."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
