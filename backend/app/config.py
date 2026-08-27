from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import os
import secrets

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.version import default_build_time, default_git_commit, default_version


def _first_non_empty_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return ""


def default_agent_version() -> str:
    # Agent 是服务器基础设施，版本独立于平台 APP_VERSION。
    return _first_non_empty_env("AGENT_AGENT_VERSION", "CRAWLER_AGENT_VERSION") or "1.1.2"


def default_agent_image() -> str:
    version = default_agent_version()
    return _first_non_empty_env("CRAWLER_AGENT_IMAGE", "AGENT_IMAGE") or f"crawler_platform_agent:{version}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "crawler_platform"
    app_env: str = "production"
    app_version: str = Field(default_factory=default_version)
    app_git_commit: str = Field(default_factory=default_git_commit)
    app_build_time: str = Field(default_factory=default_build_time)
    timezone: str = "Asia/Shanghai"
    api_prefix: str = "/api/v1"
    control_plane_public_base_url: str = Field(default_factory=lambda: os.getenv("CRAWLER_CONTROL_PUBLIC_BASE_URL", os.getenv("CONTROL_PLANE_PUBLIC_BASE_URL", "")))
    crawler_agent_version: str = Field(default_factory=default_agent_version)
    crawler_agent_image: str = Field(default_factory=default_agent_image)
    crawler_agent_image_digest: str = Field(default_factory=lambda: os.getenv("CRAWLER_AGENT_IMAGE_DIGEST", ""))
    crawler_agent_registry_public_host: str = Field(default_factory=lambda: os.getenv("CRAWLER_AGENT_REGISTRY_PUBLIC_HOST", ""))
    crawler_agent_registry_port: int = int(os.getenv("CRAWLER_AGENT_REGISTRY_PORT", "5000"))
    crawler_agent_registry_auth_enabled: bool = Field(default_factory=lambda: os.getenv("CRAWLER_AGENT_REGISTRY_AUTH_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"})
    crawler_agent_registry_tls_enabled: bool = Field(default_factory=lambda: os.getenv("CRAWLER_AGENT_REGISTRY_TLS_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"})

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

    platform_action_enabled: bool = Field(default_factory=lambda: os.getenv("CRAWLER_PLATFORM_ACTIONS_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"})
    platform_action_root: str = Field(default_factory=lambda: os.getenv("CRAWLER_PLATFORM_ACTION_ROOT", "/data/projects/crawler_platform"))
    platform_action_timeout_seconds: int = int(os.getenv("CRAWLER_PLATFORM_ACTION_TIMEOUT_SECONDS", "1800"))

    # Platform-managed spider project build center. This is deliberately host/env driven
    # until repository and registry credential models are implemented in the control plane.
    crawler_project_build_enabled: bool = Field(default_factory=lambda: os.getenv("CRAWLER_PROJECT_BUILD_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"})
    crawler_project_build_root: Path = Field(default_factory=lambda: Path(os.getenv("CRAWLER_PROJECT_BUILD_ROOT", "/data/project-builds")))
    crawler_project_build_timeout_seconds: int = int(os.getenv("CRAWLER_PROJECT_BUILD_TIMEOUT_SECONDS", "1800"))
    crawler_project_build_stale_seconds: int = int(os.getenv("CRAWLER_PROJECT_BUILD_STALE_SECONDS", str(max(1860, int(os.getenv("CRAWLER_PROJECT_BUILD_TIMEOUT_SECONDS", "1800")) + 60))))
    crawler_project_image_repository_prefix: str = Field(default_factory=lambda: os.getenv("CRAWLER_PROJECT_IMAGE_REPOSITORY_PREFIX", ""))
    crawler_project_build_platform: str = Field(default_factory=lambda: os.getenv("CRAWLER_PROJECT_BUILD_PLATFORM", "linux/amd64"))
    crawler_project_build_pip_index_url: str = Field(default_factory=lambda: os.getenv("CRAWLER_PROJECT_BUILD_PIP_INDEX_URL", os.getenv("PIP_INDEX_URL", "https://pypi.tuna.tsinghua.edu.cn/simple")))
    crawler_project_git_clone_attempts: int = int(os.getenv("CRAWLER_PROJECT_GIT_CLONE_ATTEMPTS", "3"))
    crawler_project_git_clone_retry_seconds: int = int(os.getenv("CRAWLER_PROJECT_GIT_CLONE_RETRY_SECONDS", "5"))
    crawler_project_git_clone_timeout_seconds: int = int(os.getenv("CRAWLER_PROJECT_GIT_CLONE_TIMEOUT_SECONDS", "300"))
    crawler_project_source_archive_fallback_enabled: bool = Field(default_factory=lambda: os.getenv("CRAWLER_PROJECT_SOURCE_ARCHIVE_FALLBACK_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"})
    crawler_project_source_archive_attempts: int = int(os.getenv("CRAWLER_PROJECT_SOURCE_ARCHIVE_ATTEMPTS", "1"))
    crawler_project_source_archive_timeout_seconds: int = int(os.getenv("CRAWLER_PROJECT_SOURCE_ARCHIVE_TIMEOUT_SECONDS", "120"))

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
