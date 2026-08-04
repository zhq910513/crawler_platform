from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.utils import utcnow

BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class SysUser(Base, TimestampMixin):
    __tablename__ = "sys_user"
    user_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="SET NULL"), index=True)
    user_name: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    nick_name: Mapped[str] = mapped_column(String(50), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_type: Mapped[str] = mapped_column(String(30), default="NORMAL_USER", index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ENABLED", index=True, nullable=False)
    last_login_ip: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    current_session_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    password_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SysUserSession(Base, TimestampMixin):
    __tablename__ = "sys_user_session"
    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="CASCADE"), index=True, nullable=False)
    company_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="SET NULL"), index=True)
    token_jti: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    session_status: Mapped[str] = mapped_column(String(30), default="ACTIVE", index=True, nullable=False)
    login_time: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)
    logout_time: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoke_reason: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    login_ip: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    user_agent: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    device_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)


class SysLoginLog(Base):
    __tablename__ = "sys_login_log"
    login_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="SET NULL"), index=True)
    user_name: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    ip_address: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    user_agent: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="SUCCESS", index=True, nullable=False)
    message: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)


class SysOperationLog(Base):
    __tablename__ = "sys_operation_log"
    operation_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="SET NULL"), index=True)
    user_name: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    operation_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    resource_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    request_method: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    request_path: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    before_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    ip_address: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="SUCCESS", index=True, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)


class SysConfig(Base, TimestampMixin):
    __tablename__ = "sys_config"
    config_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    config_name: Mapped[str] = mapped_column(String(100), nullable=False)
    config_value: Mapped[str] = mapped_column(Text, default="", nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)


class SysSecret(Base, TimestampMixin):
    __tablename__ = "sys_secret"
    secret_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), index=True)
    secret_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    secret_name: Mapped[str] = mapped_column(String(100), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CrawlerCompany(Base, TimestampMixin):
    __tablename__ = "crawler_company"
    company_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    company_name: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ENABLED", index=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), default="Asia/Shanghai", nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="SET NULL"))


class CrawlerServer(Base, TimestampMixin):
    __tablename__ = "crawler_server"
    server_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    server_code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    server_name: Mapped[str] = mapped_column(String(100), nullable=False)
    server_ip: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    environment: Mapped[str] = mapped_column(String(30), default="production", index=True, nullable=False)
    max_container_slots: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    manage_status: Mapped[str] = mapped_column(String(20), default="ENABLED", index=True, nullable=False)
    health_status: Mapped[str] = mapped_column(String(20), default="UNKNOWN", index=True, nullable=False)
    capacity_status: Mapped[str] = mapped_column(String(20), default="UNKNOWN", index=True, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    agent: Mapped["CrawlerAgent | None"] = relationship(back_populates="server", uselist=False)


class CrawlerAgent(Base, TimestampMixin):
    __tablename__ = "crawler_agent"
    agent_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    server_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_server.server_id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    agent_code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    agent_version: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    protocol_version: Mapped[str] = mapped_column(String(30), default="3.0", nullable=False)
    agent_instance_id: Mapped[str] = mapped_column(String(100), default="", index=True, nullable=False)
    connection_status: Mapped[str] = mapped_column(String(20), default="UNREGISTERED", index=True, nullable=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    heartbeat_interval_seconds: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    current_runs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    server: Mapped[CrawlerServer] = relationship(back_populates="agent")


class CrawlerCompanyDiscoveryToken(Base, TimestampMixin):
    __tablename__ = "crawler_company_discovery_token"
    token_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    token_name: Mapped[str] = mapped_column(String(120), default="default", nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ENABLED", index=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)


class CrawlerDiscoveredProject(Base, TimestampMixin):
    __tablename__ = "crawler_discovered_project"
    __table_args__ = (UniqueConstraint("company_id", "project_key", name="uk_discovered_company_project_key"),)
    discovered_project_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    project_key: Mapped[str] = mapped_column(String(200), nullable=False)
    project_code: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    project_name: Mapped[str] = mapped_column(String(150), nullable=False)
    repository_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    image_repository: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    latest_release_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_project_release.release_id", ondelete="SET NULL"), index=True)
    latest_version: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    latest_image_digest: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    discovery_status: Mapped[str] = mapped_column(String(30), default="DISCOVERED", index=True, nullable=False)
    parse_status: Mapped[str] = mapped_column(String(30), default="UNKNOWN", index=True, nullable=False)
    parse_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    first_deployed_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_deployed_at: Mapped[datetime | None] = mapped_column(DateTime)
    formal_project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="SET NULL"), index=True)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class CrawlerDiscoveredProjectServer(Base, TimestampMixin):
    __tablename__ = "crawler_discovered_project_server"
    __table_args__ = (UniqueConstraint("discovered_project_id", "server_id", name="uk_discovered_project_server"),)
    discovered_project_server_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    discovered_project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_discovered_project.discovered_project_id", ondelete="CASCADE"), index=True, nullable=False)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    server_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_server.server_id", ondelete="CASCADE"), index=True, nullable=False)
    deployment_status: Mapped[str] = mapped_column(String(30), default="DEPLOYED", index=True, nullable=False)
    latest_image_digest: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    last_deployed_at: Mapped[datetime | None] = mapped_column(DateTime)


class CrawlerProject(Base, TimestampMixin):
    __tablename__ = "crawler_project"
    __table_args__ = (UniqueConstraint("company_id", "project_code", name="uk_project_company_code"),)
    project_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="RESTRICT"), index=True, nullable=False)
    discovered_project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_discovered_project.discovered_project_id", ondelete="SET NULL"), index=True)
    project_key: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    project_code: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    project_name: Mapped[str] = mapped_column(String(150), nullable=False)
    remark: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    repository_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    image_repository: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ENABLED", index=True, nullable=False)
    online_status: Mapped[str] = mapped_column(String(30), default="READY", index=True, nullable=False)
    dispatch_mode: Mapped[str] = mapped_column(String(30), default="LOAD_BALANCE", index=True, nullable=False)
    min_available_servers: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_active_servers: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    allow_deployed_fallback: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_company_pool_fallback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_runtime_mode: Mapped[str] = mapped_column(String(40), default="SHARED_ENV_ISOLATED", index=True, nullable=False)
    default_task_max_concurrency: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    default_group_max_concurrency: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    default_shm_size_mb: Mapped[int] = mapped_column(Integer, default=64, nullable=False)
    default_log_limit_mb: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    container_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="SET NULL"))


class CrawlerProjectMember(Base, TimestampMixin):
    __tablename__ = "crawler_project_member"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uk_project_user"),)
    member_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="VIEWER", index=True, nullable=False)


class CrawlerProjectServer(Base, TimestampMixin):
    __tablename__ = "crawler_project_server"
    __table_args__ = (UniqueConstraint("project_id", "server_id", name="uk_project_server"),)
    project_server_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), index=True, nullable=False)
    server_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_server.server_id", ondelete="CASCADE"), index=True, nullable=False)
    deployment_status: Mapped[str] = mapped_column(String(30), default="DEPLOYED", index=True, nullable=False)
    scheduling_status: Mapped[str] = mapped_column(String(30), default="ENABLED", index=True, nullable=False)
    image_readiness_status: Mapped[str] = mapped_column(String(30), default="UNKNOWN", index=True, nullable=False)
    server_role: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    auto_eject_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_recover_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    latest_release_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_project_release.release_id", ondelete="SET NULL"), index=True)
    latest_image_digest: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    last_deployed_at: Mapped[datetime | None] = mapped_column(DateTime)
    disabled_reason: Mapped[str] = mapped_column(String(500), default="", nullable=False)


class CrawlerImageArtifact(Base, TimestampMixin):
    __tablename__ = "crawler_image_artifact"
    __table_args__ = (UniqueConstraint("image_repository", "image_digest", name="uk_image_repository_digest"),)
    artifact_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    image_repository: Mapped[str] = mapped_column(String(500), index=True, nullable=False)
    image_tag: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    image_digest: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    supported_arch: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    git_commit: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    build_time: Mapped[datetime | None] = mapped_column(DateTime)
    artifact_metadata: Mapped[dict[str, Any]] = mapped_column("artifact_metadata", JSON, default=dict, nullable=False)


class CrawlerProjectRelease(Base, TimestampMixin):
    __tablename__ = "crawler_project_release"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uk_project_release_version"), UniqueConstraint("discovered_project_id", "version", name="uk_discovered_release_version"))
    release_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), index=True)
    discovered_project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_discovered_project.discovered_project_id", ondelete="CASCADE"), index=True)
    artifact_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_image_artifact.artifact_id", ondelete="SET NULL"), index=True)
    version: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    release_channel: Mapped[str] = mapped_column(String(50), default="stable", index=True, nullable=False)
    image_repository: Mapped[str] = mapped_column(String(500), nullable=False)
    image_digest: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    git_branch: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    git_commit: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    manifest_version: Mapped[str] = mapped_column(String(30), default="1", nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    release_status: Mapped[str] = mapped_column(String(30), default="PUBLISHED", index=True, nullable=False)
    parse_status: Mapped[str] = mapped_column(String(30), default="SUCCESS", index=True, nullable=False)
    parse_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)


class CrawlerReleaseChannel(Base, TimestampMixin):
    __tablename__ = "crawler_release_channel"
    __table_args__ = (UniqueConstraint("project_id", "channel_name", name="uk_project_channel"),)
    channel_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), index=True, nullable=False)
    channel_name: Mapped[str] = mapped_column(String(50), default="stable", nullable=False)
    release_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_project_release.release_id", ondelete="SET NULL"), index=True)
    channel_status: Mapped[str] = mapped_column(String(20), default="ENABLED", index=True, nullable=False)


class CrawlerProjectTaskDefinition(Base, TimestampMixin):
    __tablename__ = "crawler_project_task_definition"
    __table_args__ = (UniqueConstraint("project_id", "definition_key", name="uk_project_definition_key"),)
    definition_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), index=True, nullable=False)
    latest_release_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_project_release.release_id", ondelete="SET NULL"), index=True)
    definition_key: Mapped[str] = mapped_column(String(200), nullable=False)
    task_name: Mapped[str] = mapped_column(String(200), nullable=False)
    entry_module: Mapped[str] = mapped_column(String(300), nullable=False)
    entry_function: Mapped[str] = mapped_column(String(120), nullable=False)
    source_file: Mapped[str] = mapped_column(String(300), default="sch.py", nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    default_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    suggested_cron: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(20), default="SINGLE", index=True, nullable=False)
    idempotency_policy: Mapped[str] = mapped_column(String(30), default="IDEMPOTENT", index=True, nullable=False)
    resource_requirements: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    required_capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    runtime_mode: Mapped[str] = mapped_column(String(40), default="SHARED_ENV_ISOLATED", index=True, nullable=False)
    task_group: Mapped[str] = mapped_column(String(100), default="default", index=True, nullable=False)
    task_max_concurrency: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    group_max_concurrency: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    exclusive_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    io_class: Mapped[str] = mapped_column(String(30), default="NORMAL", index=True, nullable=False)
    shm_size_mb: Mapped[int] = mapped_column(Integer, default=64, nullable=False)
    log_limit_mb: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    resource_locks: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    secret_refs: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    definition_status: Mapped[str] = mapped_column(String(30), default="AVAILABLE", index=True, nullable=False)
    parse_message: Mapped[str] = mapped_column(Text, default="", nullable=False)


class CrawlerTask(Base, TimestampMixin):
    __tablename__ = "crawler_task"
    __table_args__ = (UniqueConstraint("project_id", "definition_id", name="uk_project_definition_task"), UniqueConstraint("project_id", "task_code", name="uk_project_task_code"))
    task_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), index=True, nullable=False)
    definition_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_project_task_definition.definition_id", ondelete="SET NULL"), index=True)
    owner_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="SET NULL"), index=True)
    task_code: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    task_name: Mapped[str] = mapped_column(String(200), nullable=False)
    entry_module: Mapped[str] = mapped_column(String(300), nullable=False)
    entry_function: Mapped[str] = mapped_column(String(120), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(20), default="SINGLE", index=True, nullable=False)
    shard_strategy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    required_node_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_parallel_nodes: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    required_capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    runtime_mode: Mapped[str] = mapped_column(String(40), default="SHARED_ENV_ISOLATED", index=True, nullable=False)
    task_group: Mapped[str] = mapped_column(String(100), default="default", index=True, nullable=False)
    task_max_concurrency: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    group_max_concurrency: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    exclusive_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    io_class: Mapped[str] = mapped_column(String(30), default="NORMAL", index=True, nullable=False)
    shm_size_mb: Mapped[int] = mapped_column(Integer, default=64, nullable=False)
    log_limit_mb: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    resource_locks: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    idempotency_policy: Mapped[str] = mapped_column(String(30), default="IDEMPOTENT", index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True, nullable=False)
    image_policy: Mapped[str] = mapped_column(String(30), default="RELEASE_CHANNEL", nullable=False)
    release_channel: Mapped[str] = mapped_column(String(50), default="stable", nullable=False)
    fixed_release_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_project_release.release_id", ondelete="SET NULL"), index=True)
    cpu_limit: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    memory_limit_mb: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    max_retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="", nullable=False)


class CrawlerTaskSchedule(Base, TimestampMixin):
    __tablename__ = "crawler_task_schedule"
    schedule_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), index=True, nullable=False)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_task.task_id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    schedule_status: Mapped[str] = mapped_column(String(20), default="PAUSED", index=True, nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(20), default="MANUAL", nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    schedule_timezone: Mapped[str] = mapped_column(String(100), default="Asia/Shanghai", nullable=False)
    overlap_policy: Mapped[str] = mapped_column(String(30), default="QUEUE", nullable=False)
    schedule_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    schedule_label: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime)


class CrawlerTaskServerTarget(Base, TimestampMixin):
    __tablename__ = "crawler_task_server_target"
    __table_args__ = (UniqueConstraint("task_id", "server_id", name="uk_task_server_target"),)
    target_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_task.task_id", ondelete="CASCADE"), index=True, nullable=False)
    server_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_server.server_id", ondelete="CASCADE"), index=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CrawlerTaskRun(Base, TimestampMixin):
    __tablename__ = "crawler_task_run"
    __table_args__ = (UniqueConstraint("task_id", "trigger_key", name="uk_task_trigger_key"),)
    run_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), index=True, nullable=False)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_task.task_id", ondelete="CASCADE"), index=True, nullable=False)
    schedule_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_task_schedule.schedule_id", ondelete="SET NULL"), index=True)
    parent_run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_task_run.run_id", ondelete="SET NULL"), index=True)
    root_run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_task_run.run_id", ondelete="SET NULL"), index=True)
    server_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_server.server_id", ondelete="SET NULL"), index=True)
    agent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_agent.agent_id", ondelete="SET NULL"), index=True)
    release_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_project_release.release_id", ondelete="SET NULL"), index=True)
    image_repository: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    image_digest: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    entry_module: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    entry_function: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(20), default="SINGLE", index=True, nullable=False)
    shard_index: Mapped[int | None] = mapped_column(Integer)
    shard_count: Mapped[int | None] = mapped_column(Integer)
    trigger_type: Mapped[str] = mapped_column(String(30), default="SCHEDULE", index=True, nullable=False)
    idempotency_policy: Mapped[str] = mapped_column(String(30), default="IDEMPOTENT", index=True, nullable=False)
    cpu_limit: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    memory_limit_mb: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    runtime_mode: Mapped[str] = mapped_column(String(40), default="SHARED_ENV_ISOLATED", index=True, nullable=False)
    task_group: Mapped[str] = mapped_column(String(100), default="default", index=True, nullable=False)
    task_max_concurrency: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    group_max_concurrency: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    exclusive_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    io_class: Mapped[str] = mapped_column(String(30), default="NORMAL", index=True, nullable=False)
    shm_size_mb: Mapped[int] = mapped_column(Integer, default=64, nullable=False)
    log_limit_mb: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    resource_locks: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    run_status: Mapped[str] = mapped_column(String(30), default="QUEUED", index=True, nullable=False)
    routing_status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True, nullable=False)
    routing_reason: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    trigger_key: Mapped[str | None] = mapped_column(String(220), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lease_token: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    parameters_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    retry_reason: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    log_status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True, nullable=False)
    log_storage_type: Mapped[str] = mapped_column(String(30), default="DB_CHUNK", nullable=False)
    log_path: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    log_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    log_lines: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_log_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_log_at: Mapped[datetime | None] = mapped_column(DateTime)
    log_truncated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failed_stage: Mapped[str] = mapped_column(String(80), default="", index=True, nullable=False)
    error_type: Mapped[str] = mapped_column(String(100), default="", index=True, nullable=False)
    error_summary: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    retryable: Mapped[bool | None] = mapped_column(Boolean)
    diagnosis_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)


class CrawlerRunEvent(Base):
    __tablename__ = "crawler_run_event"
    event_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_task_run.run_id", ondelete="CASCADE"), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    event_level: Mapped[str] = mapped_column(String(20), default="INFO", index=True, nullable=False)
    stage: Mapped[str] = mapped_column(String(80), default="", index=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)


class CrawlerRunLogChunk(Base):
    __tablename__ = "crawler_run_log_chunk"
    __table_args__ = (UniqueConstraint("run_id", "stream", "seq", name="uk_run_log_chunk_seq"),)
    chunk_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_task_run.run_id", ondelete="CASCADE"), index=True, nullable=False)
    stream: Mapped[str] = mapped_column(String(20), default="stdout", index=True, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    offset_start: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    offset_end: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    content_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)


class CrawlerRunLog(Base):
    __tablename__ = "crawler_run_log"
    log_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_task_run.run_id", ondelete="CASCADE"), index=True, nullable=False)
    log_level: Mapped[str] = mapped_column(String(20), default="INFO", index=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)


class SysNotificationChannel(Base, TimestampMixin):
    __tablename__ = "sys_notification_channel"
    channel_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    scope_type: Mapped[str] = mapped_column(String(20), default="SYSTEM", index=True, nullable=False)
    company_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), index=True)
    channel_name: Mapped[str] = mapped_column(String(100), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    channel_status: Mapped[str] = mapped_column(String(20), default="DISABLED", index=True, nullable=False)
    config_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)
    p0_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_test_result: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=1800, nullable=False)


class SysAlertEvent(Base, TimestampMixin):
    __tablename__ = "sys_alert_event"
    __table_args__ = (UniqueConstraint("fingerprint", "alert_status", name="uk_alert_fingerprint_status"),)
    alert_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), index=True)
    severity: Mapped[str] = mapped_column(String(10), default="P2", index=True, nullable=False)
    alert_status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True, nullable=False)
    alert_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime)
    notify_after_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    alert_metadata: Mapped[dict[str, Any]] = mapped_column("alert_metadata", JSON, default=dict, nullable=False)


class SysAlertDelivery(Base, TimestampMixin):
    __tablename__ = "sys_alert_delivery"
    delivery_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_alert_event.alert_id", ondelete="CASCADE"), index=True, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_notification_channel.channel_id", ondelete="CASCADE"), index=True, nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)


Index("idx_server_company_manage", CrawlerServer.company_id, CrawlerServer.manage_status)
Index("idx_project_company_status", CrawlerProject.company_id, CrawlerProject.status, CrawlerProject.online_status)
Index("idx_project_server_route", CrawlerProjectServer.project_id, CrawlerProjectServer.scheduling_status, CrawlerProjectServer.image_readiness_status)
Index("idx_task_company_status", CrawlerTask.company_id, CrawlerTask.status)
Index("idx_task_group_limits", CrawlerTask.company_id, CrawlerTask.project_id, CrawlerTask.task_group)
Index("idx_run_route", CrawlerTaskRun.run_status, CrawlerTaskRun.routing_status, CrawlerTaskRun.server_id)
Index("idx_run_task_group_active", CrawlerTaskRun.project_id, CrawlerTaskRun.task_group, CrawlerTaskRun.run_status)
Index("idx_run_event_run_created", CrawlerRunEvent.run_id, CrawlerRunEvent.created_at)
Index("idx_run_log_chunk_run_seq", CrawlerRunLogChunk.run_id, CrawlerRunLogChunk.seq)
Index("idx_session_user_status", SysUserSession.user_id, SysUserSession.session_status, SysUserSession.last_active_at)
