from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import os
import secrets

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "crawler_platform"
    app_env: str = "production"
    app_version: str = "1.0.2"
    app_git_commit: str = "unknown"
    app_build_time: str = "unknown"
    timezone: str = "Asia/Shanghai"
    api_prefix: str = "/api/v1"
    platform_public_url: str = ""

    database_url: str = Field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite+pysqlite:///./crawler_platform_dev.db" if os.getenv("APP_ENV", "production").lower() not in {"production", "prod"} else ""))
    redis_url: str = Field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0" if os.getenv("APP_ENV", "production").lower() not in {"production", "prod"} else ""))

    jwt_secret: str = Field(default_factory=lambda: os.getenv("JWT_SECRET", secrets.token_urlsafe(48) if os.getenv("APP_ENV", "production").lower() not in {"production", "prod"} else ""))
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    session_active_minutes: int = 10
    force_login_token_minutes: int = 2

    secret_encryption_key: str = Field(default_factory=lambda: os.getenv("SECRET_ENCRYPTION_KEY", secrets.token_urlsafe(48) if os.getenv("APP_ENV", "production").lower() not in {"production", "prod"} else ""))
    admin_username: str = "admin"
    admin_password: str = Field(default_factory=lambda: os.getenv("ADMIN_PASSWORD", "Admin@123456" if os.getenv("APP_ENV", "production").lower() not in {"production", "prod"} else ""))
    admin_nickname: str = "超级管理员"

    agent_lease_seconds: int = 90
    agent_stale_seconds: int = 60
    agent_offline_seconds: int = 120
    scheduler_poll_seconds: int = 5
    scheduler_lock_seconds: int = 60

    task_log_root: Path = Path("/data/task-logs")
    task_log_retention_days: int = 30
    metric_retention_days: int = 14
    sse_poll_seconds: float = 0.5
    sse_keepalive_seconds: int = 15

    cors_origins: str = ""
    enable_api_docs: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        value = self.cors_origins.strip()
        if value == "*":
            return ["*"]
        return [item.strip() for item in value.split(",") if item.strip()]

    def validate_runtime(self) -> None:
        if self.app_env.lower() not in {"production", "prod"}:
            return
        failures: list[str] = []
        checks = {
            "JWT_SECRET": (self.jwt_secret, 32),
            "SECRET_ENCRYPTION_KEY": (self.secret_encryption_key, 32),
            "ADMIN_PASSWORD": (self.admin_password, 12),
            "DATABASE_URL": (self.database_url, 12),
            "REDIS_URL": (self.redis_url, 8),
        }
        for name, (value, minimum) in checks.items():
            lowered = value.lower()
            if len(value) < minimum or "change-this" in lowered or "replacewith" in lowered:
                failures.append(name)
        if self.database_url.startswith("sqlite"):
            failures.append("DATABASE_URL")
        if self.redis_url.startswith("redis://localhost") or "crawler@redis" in self.redis_url:
            failures.append("REDIS_URL")
        if failures:
            raise RuntimeError("production configuration is unsafe or incomplete: " + ", ".join(sorted(set(failures))))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
