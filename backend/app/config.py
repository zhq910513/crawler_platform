from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "crawler_platform"
    app_env: str = "production"
    app_version: str = "1.0.0"
    timezone: str = "Asia/Shanghai"
    api_prefix: str = "/api"

    database_url: str = "mysql+pymysql://crawler_platform:crawler_platform@mysql:3306/crawler_platform?charset=utf8mb4"
    redis_url: str = "redis://:crawler@redis:6379/0"

    jwt_secret: str = Field(default="change-this-jwt-secret-at-least-32-characters")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720

    secret_encryption_key: str = Field(default="change-this-secret-encryption-master-key")
    admin_username: str = "admin"
    admin_password: str = "Admin@123456"
    admin_nickname: str = "超级管理员"

    cicd_token: str = "change-this-cicd-token"
    agent_bootstrap_token: str = "change-this-agent-bootstrap-token"
    agent_lease_seconds: int = 90
    scheduler_poll_seconds: int = 5
    scheduler_lock_seconds: int = 60

    task_log_root: Path = Path("/data/task-logs")
    task_log_retention_days: int = 30
    metric_retention_days: int = 14

    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        value = self.cors_origins.strip()
        if value == "*":
            return ["*"]
        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
