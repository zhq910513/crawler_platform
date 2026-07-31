from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
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
    user_name: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    nick_name: Mapped[str] = mapped_column(String(50), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_type: Mapped[str] = mapped_column(String(20), default="NORMAL_USER", index=True, nullable=False)
    status: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    last_login_ip: Mapped[str | None] = mapped_column(String(128))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)


class SysLoginLog(Base):
    __tablename__ = "sys_login_log"
    login_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="SET NULL"))
    user_name: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    ip_address: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    user_agent: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="SUCCESS", index=True, nullable=False)
    message: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)


class SysOperationLog(Base):
    __tablename__ = "sys_operation_log"
    operation_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="SET NULL"))
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
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="SET NULL"))


class CrawlerCompanyMember(Base, TimestampMixin):
    __tablename__ = "crawler_company_member"
    __table_args__ = (UniqueConstraint("company_id", "user_id", name="uk_company_user"),)
    member_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="MEMBER", index=True, nullable=False)


class CrawlerProject(Base, TimestampMixin):
    __tablename__ = "crawler_project"
    project_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="RESTRICT"), index=True, nullable=False)
    project_code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    project_name: Mapped[str] = mapped_column(String(150), nullable=False)
    remark: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    registry: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    repository: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    default_branch: Mapped[str] = mapped_column(String(100), default="main", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ENABLED", index=True, nullable=False)
    deployment_mode: Mapped[str] = mapped_column(String(30), default="BOOTSTRAP", index=True, nullable=False)
    online_status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True, nullable=False)
    min_agent_version: Mapped[str] = mapped_column(String(50), default="2.0.0", nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="SET NULL"))


class CrawlerProjectMember(Base, TimestampMixin):
    __tablename__ = "crawler_project_member"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uk_project_user"),)
    member_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="VIEWER", index=True, nullable=False)


class CrawlerServer(Base, TimestampMixin):
    __tablename__ = "crawler_server"
    server_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    server_code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    server_name: Mapped[str] = mapped_column(String(100), nullable=False)
    server_ip: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    environment: Mapped[str] = mapped_column(String(30), default="production", index=True, nullable=False)
    max_container_slots: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ONLINE", index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    agent: Mapped["CrawlerAgent | None"] = relationship(back_populates="server", uselist=False)


class CrawlerAgent(Base, TimestampMixin):
    __tablename__ = "crawler_agent"
    agent_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    server_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_server.server_id", ondelete="CASCADE"), unique=True)
    agent_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    protocol_version: Mapped[str] = mapped_column(String(20), default="2.0", nullable=False)
    instance_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    agent_version: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    os_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    python_version: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    docker_version: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    cpu_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memory_total_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    capabilities_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    labels_json: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ONLINE", index=True, nullable=False)
    last_ip: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    server: Mapped[CrawlerServer] = relationship(back_populates="agent")


class CrawlerServerMetric(Base):
    __tablename__ = "crawler_server_metric"
    __table_args__ = (Index("idx_metric_server_time", "server_id", "recorded_at"),)
    metric_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    server_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_server.server_id", ondelete="CASCADE"), nullable=False)
    cpu_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, nullable=False)
    memory_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, nullable=False)
    disk_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, nullable=False)
    load_1m: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    load_5m: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    network_sent_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    network_received_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    running_task_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    process_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    docker_image_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)


# 旧镜像表保留用于无损升级，V2 任务不再依赖它。
class CrawlerImageVersion(Base):
    __tablename__ = "crawler_image_version"
    __table_args__ = (UniqueConstraint("project_id", "image_digest", name="uk_project_image_digest"),)
    image_version_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), nullable=False)
    image_tag: Mapped[str] = mapped_column(String(255), nullable=False)
    image_digest: Mapped[str] = mapped_column(String(255), nullable=False)
    git_branch: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    git_commit: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    pipeline_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    build_status: Mapped[str] = mapped_column(String(20), default="SUCCESS", index=True, nullable=False)
    build_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    built_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class CrawlerSpiderRelease(Base, TimestampMixin):
    __tablename__ = "crawler_spider_release"
    __table_args__ = (
        UniqueConstraint("app_name", "version", name="uk_spider_app_version"),
        UniqueConstraint("image_repository", "image_digest", name="uk_spider_image_digest"),
    )
    release_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    app_name: Mapped[str] = mapped_column(String(100), default="crawler_platform_spiders", index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    image_repository: Mapped[str] = mapped_column(String(500), nullable=False)
    image_tag: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    image_digest: Mapped[str] = mapped_column(String(255), nullable=False)
    git_commit: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class CrawlerSpiderEntry(Base, TimestampMixin):
    __tablename__ = "crawler_spider_entry"
    __table_args__ = (UniqueConstraint("release_id", "task_name", name="uk_release_task_name"),)
    entry_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    release_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_spider_release.release_id", ondelete="CASCADE"), nullable=False)
    task_name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    image_profile: Mapped[str] = mapped_column(String(20), default="api", nullable=False)
    parameter_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    required_resources: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    default_timeout_seconds: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)


class CrawlerReleaseChannel(Base, TimestampMixin):
    __tablename__ = "crawler_release_channel"
    __table_args__ = (UniqueConstraint("project_id", "channel_name", name="uk_project_channel"),)
    channel_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), nullable=False)
    channel_name: Mapped[str] = mapped_column(String(50), nullable=False)
    image_version_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_image_version.image_version_id"))
    spider_release_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_spider_release.release_id"))


class CrawlerTask(Base, TimestampMixin):
    __tablename__ = "crawler_task"
    task_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="RESTRICT"), index=True, nullable=False)
    task_code: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    task_name: Mapped[str] = mapped_column(String(200), nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id"), nullable=False)
    spider_task_name: Mapped[str] = mapped_column(String(200), default="", index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(100), default="", index=True, nullable=False)
    task_group: Mapped[str] = mapped_column(String(100), default="default", index=True, nullable=False)
    developer: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    entry_module: Mapped[str] = mapped_column(String(300), default="", index=True, nullable=False)
    entry_function: Mapped[str] = mapped_column(String(120), default="", index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), default="MANUAL", index=True, nullable=False)
    source_file: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    resource_requirements: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # 旧动态入口字段仅为迁移保留，V2 API 始终清空。
    executor_type: Mapped[str] = mapped_column(String(30), default="SPIDER_ENTRY", nullable=False)
    entrypoint: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    arguments: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    keyword_arguments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    related_tables: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ENABLED", index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="SET NULL"))
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="SET NULL"))
    runtime: Mapped["CrawlerTaskRuntime | None"] = relationship(back_populates="task", uselist=False, cascade="all, delete-orphan")
    schedule: Mapped["CrawlerTaskSchedule | None"] = relationship(back_populates="task", uselist=False, cascade="all, delete-orphan")
    targets: Mapped[list["CrawlerTaskTarget"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class CrawlerTaskRuntime(Base, TimestampMixin):
    __tablename__ = "crawler_task_runtime"
    runtime_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_task.task_id", ondelete="CASCADE"), unique=True, nullable=False)
    image_policy: Mapped[str] = mapped_column(String(30), default="RELEASE_CHANNEL", nullable=False)
    fixed_image_version_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_image_version.image_version_id"))
    fixed_spider_release_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_spider_release.release_id"))
    release_channel: Mapped[str] = mapped_column(String(50), default="stable", nullable=False)
    pull_policy: Mapped[str] = mapped_column(String(30), default="IF_NOT_PRESENT", nullable=False)
    cpu_limit: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=2, nullable=False)
    memory_limit_mb: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    shm_size_mb: Mapped[int] = mapped_column(Integer, default=256, nullable=False)
    pids_limit: Mapped[int] = mapped_column(Integer, default=512, nullable=False)
    stop_grace_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    auto_remove: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    keep_failed_container: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 旧危险字段保留空值，V2 不读取。
    container_command: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    container_working_dir: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    environment_variables: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    secret_refs: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    volume_mounts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    network_mode: Mapped[str] = mapped_column(String(100), default="bridge", nullable=False)
    task: Mapped[CrawlerTask] = relationship(back_populates="runtime")


class CrawlerTaskSchedule(Base, TimestampMixin):
    __tablename__ = "crawler_task_schedule"
    schedule_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_task.task_id", ondelete="CASCADE"), unique=True, nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(20), default="CRON", nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), default="Asia/Shanghai", nullable=False)
    misfire_policy: Mapped[str] = mapped_column(String(30), default="FIRE_ONCE", nullable=False)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    overlap_policy: Mapped[str] = mapped_column(String(20), default="SKIP", nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    max_retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_interval_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    retry_backoff: Mapped[str] = mapped_column(String(20), default="FIXED", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime)
    task: Mapped[CrawlerTask] = relationship(back_populates="schedule")


class CrawlerTaskTarget(Base):
    __tablename__ = "crawler_task_target"
    __table_args__ = (UniqueConstraint("task_id", "server_id", name="uk_task_server"),)
    target_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_task.task_id", ondelete="CASCADE"), nullable=False)
    server_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_server.server_id", ondelete="CASCADE"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    task: Mapped[CrawlerTask] = relationship(back_populates="targets")


class CrawlerTaskRun(Base, TimestampMixin):
    __tablename__ = "crawler_task_run"
    __table_args__ = (
        UniqueConstraint("schedule_id", "scheduled_at", "attempt", name="uk_schedule_time_attempt"),
        UniqueConstraint("parent_run_id", name="uk_run_parent_retry"),
        Index("idx_run_server_status", "server_id", "status"),
        Index("idx_run_project_created", "project_id", "created_at"),
        Index("idx_run_status_lease", "status", "lease_expires_at"),
    )
    run_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    run_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id"), index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id"), index=True, nullable=False)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_task.task_id"), nullable=False)
    schedule_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_task_schedule.schedule_id"))
    server_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_server.server_id"), nullable=False)
    agent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_agent.agent_id"))
    spider_release_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_spider_release.release_id"))
    spider_entry_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_spider_entry.entry_id"))
    trigger_type: Mapped[str] = mapped_column(String(20), default="SCHEDULE", nullable=False)
    triggered_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="SET NULL"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime)
    starting_at: Mapped[datetime | None] = mapped_column(DateTime)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    lost_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(30), default="QUEUED", index=True, nullable=False)
    desired_action: Mapped[str] = mapped_column(String(20), default="NONE", nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    parent_run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_task_run.run_id"))
    root_run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_task_run.run_id"))
    lease_token: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    container_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    container_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    image_name: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    image_tag: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    image_digest: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    git_commit: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    oom_killed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    error_type: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_error_event_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    last_error_code: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    last_error_type: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    last_error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error_log_seq: Mapped[int | None] = mapped_column(BigInteger)
    terminal_error_code: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    terminal_error_type: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    terminal_error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    terminal_error_retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    terminal_error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    task_spec_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    resource_manifest_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    runtime_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    log_path: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    log_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_log_at: Mapped[datetime | None] = mapped_column(DateTime)
    stdout_ack_seq: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    stderr_ack_seq: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    inspect_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class CrawlerTaskRunEvent(Base):
    __tablename__ = "crawler_task_run_event"
    __table_args__ = (
        UniqueConstraint("run_id", "event_uid", name="uk_run_event_uid"),
        UniqueConstraint("run_id", "stream", "seq", name="uk_run_stream_seq"),
        Index("idx_run_event_time", "run_id", "event_id"),
    )
    event_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_task_run.run_id", ondelete="CASCADE"), nullable=False)
    event_uid: Mapped[str] = mapped_column(String(100), nullable=False)
    stream: Mapped[str] = mapped_column(String(20), default="stdout", nullable=False)
    seq: Mapped[int | None] = mapped_column(BigInteger)
    level: Mapped[str] = mapped_column(String(20), default="INFO", index=True, nullable=False)
    event_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    error_code: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    error_type: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    context_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class CrawlerContainerEvent(Base):
    __tablename__ = "crawler_container_event"
    __table_args__ = (Index("idx_container_event_run_time", "run_id", "occurred_at"),)
    event_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_task_run.run_id", ondelete="CASCADE"), nullable=False)
    server_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_server.server_id"), nullable=False)
    container_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    container_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_action: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    event_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class CrawlerProjectBootstrapToken(Base, TimestampMixin):
    __tablename__ = "crawler_project_bootstrap_token"
    __table_args__ = (Index("idx_bootstrap_token_project", "project_id", "status"),)
    token_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), index=True, nullable=False)
    token_name: Mapped[str] = mapped_column(String(120), default="default", nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    allowed_repo: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    permissions_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="SET NULL"))


class CrawlerDeploymentLog(Base, TimestampMixin):
    __tablename__ = "crawler_deployment_log"
    __table_args__ = (Index("idx_deploy_project_time", "project_id", "created_at"),)
    deployment_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), index=True, nullable=False)
    token_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_project_bootstrap_token.token_id", ondelete="SET NULL"))
    server_code: Mapped[str] = mapped_column(String(100), default="", index=True, nullable=False)
    agent_code: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    stage: Mapped[str] = mapped_column(String(50), default="BOOTSTRAP", index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    git_branch: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    git_commit: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    image_repository: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    image_digest: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    release_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_spider_release.release_id", ondelete="SET NULL"))
    preflight_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class CrawlerTaskChangeLog(Base):
    __tablename__ = "crawler_task_change_log"
    change_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_task.task_id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.user_id", ondelete="SET NULL"))
    change_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)


class CrawlerResourceConnection(Base, TimestampMixin):
    __tablename__ = "crawler_resource_connection"
    __table_args__ = (UniqueConstraint("company_id", "project_id", "connection_code", name="uk_resource_connection_scope"),)
    connection_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_company.company_id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"))
    connection_code: Mapped[str] = mapped_column(String(100), nullable=False)
    connection_name: Mapped[str] = mapped_column(String(150), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)  # MYSQL/MONGO/REDIS
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CrawlerResourceDatabase(Base, TimestampMixin):
    __tablename__ = "crawler_resource_database"
    __table_args__ = (UniqueConstraint("connection_id", "database_code", name="uk_resource_database"),)
    database_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_resource_connection.connection_id", ondelete="CASCADE"), nullable=False)
    database_code: Mapped[str] = mapped_column(String(100), nullable=False)
    database_name: Mapped[str] = mapped_column(String(200), nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class CrawlerResourceObject(Base, TimestampMixin):
    __tablename__ = "crawler_resource_object"
    __table_args__ = (UniqueConstraint("database_id", "object_code", name="uk_resource_object"),)
    object_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    database_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_resource_database.database_id", ondelete="CASCADE"), nullable=False)
    object_code: Mapped[str] = mapped_column(String(120), nullable=False)
    object_name: Mapped[str] = mapped_column(String(200), nullable=False)
    object_type: Mapped[str] = mapped_column(String(30), nullable=False)  # TABLE/COLLECTION


class CrawlerProjectResourceBinding(Base, TimestampMixin):
    __tablename__ = "crawler_project_resource_binding"
    __table_args__ = (UniqueConstraint("project_id", "logical_name", name="uk_project_resource_logical"),)
    binding_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), nullable=False)
    logical_name: Mapped[str] = mapped_column(String(200), nullable=False)
    resource_kind: Mapped[str] = mapped_column(String(30), nullable=False)  # CONNECTION/DATABASE/OBJECT
    connection_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_resource_connection.connection_id", ondelete="CASCADE"))
    database_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_resource_database.database_id", ondelete="CASCADE"))
    object_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("crawler_resource_object.object_id", ondelete="CASCADE"))


class CrawlerProjectSecretBinding(Base, TimestampMixin):
    __tablename__ = "crawler_project_secret_binding"
    __table_args__ = (UniqueConstraint("project_id", "logical_name", name="uk_project_secret_logical"),)
    binding_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crawler_project.project_id", ondelete="CASCADE"), nullable=False)
    logical_name: Mapped[str] = mapped_column(String(200), nullable=False)
    secret_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_secret.secret_id", ondelete="CASCADE"), nullable=False)
