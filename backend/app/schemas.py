from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    user_name: str
    password: str


class UserInfo(ORMModel):
    user_id: int
    user_name: str
    nick_name: str
    role_type: str
    status: bool
    last_login_at: datetime | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class UserCreate(BaseModel):
    user_name: str = Field(min_length=2, max_length=50)
    nick_name: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    role_type: Literal["SUPER_ADMIN", "NORMAL_USER"] = "NORMAL_USER"
    status: bool = True


class UserUpdate(BaseModel):
    nick_name: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role_type: Literal["SUPER_ADMIN", "NORMAL_USER"] | None = None
    status: bool | None = None


class ProjectCreate(BaseModel):
    project_code: str
    project_name: str
    registry: str
    repository: str
    default_branch: str = "main"
    status: str = "ENABLED"
    description: str = ""


class ImageVersionCreate(BaseModel):
    project_code: str
    image_tag: str
    image_digest: str
    git_branch: str = ""
    git_commit: str = ""
    pipeline_id: str = ""
    build_status: str = "SUCCESS"
    build_url: str = ""
    built_at: datetime | None = None


class RuntimePayload(BaseModel):
    image_policy: Literal["PINNED", "RELEASE_CHANNEL", "LATEST_SUCCESSFUL"] = "PINNED"
    fixed_image_version_id: int | None = None
    release_channel: str = "stable"
    pull_policy: Literal["IF_NOT_PRESENT", "ALWAYS", "NEVER"] = "IF_NOT_PRESENT"
    container_command: list[str] = Field(default_factory=list)
    container_working_dir: str = ""
    environment_variables: dict[str, str] = Field(default_factory=dict)
    secret_refs: dict[str, str] = Field(default_factory=dict)
    volume_mounts: list[dict[str, Any]] = Field(default_factory=list)
    network_mode: str = "bridge"
    cpu_limit: Decimal = Decimal("2.0")
    memory_limit_mb: int = 4096
    shm_size_mb: int = 256
    pids_limit: int = 512
    stop_grace_seconds: int = 30
    auto_remove: bool = True
    keep_failed_container: bool = False


class SchedulePayload(BaseModel):
    schedule_type: Literal["CRON", "MANUAL"] = "CRON"
    cron_expression: str = "0 20 6 * * *"
    timezone: str = "Asia/Shanghai"
    misfire_policy: Literal["FIRE_NOW", "FIRE_ONCE", "SKIP"] = "FIRE_ONCE"
    max_concurrency: int = 1
    overlap_policy: Literal["SKIP", "QUEUE", "ALLOW", "REPLACE"] = "SKIP"
    timeout_seconds: int = 3600
    max_retry_count: int = 0
    retry_interval_seconds: int = 60
    retry_backoff: Literal["FIXED", "EXPONENTIAL"] = "FIXED"
    enabled: bool = True

    @field_validator("max_concurrency")
    @classmethod
    def check_concurrency(cls, value: int) -> int:
        if value < 1 or value > 100:
            raise ValueError("最大并发数必须在 1 到 100 之间")
        return value


class TaskCreate(BaseModel):
    task_code: str
    task_name: str
    project_id: int
    platform: str = ""
    task_group: str = "default"
    developer: str = ""
    executor_type: Literal["PYTHON_METHOD", "PYTHON_MODULE", "COMMAND"] = "PYTHON_METHOD"
    entrypoint: str = ""
    arguments: list[Any] = Field(default_factory=list)
    keyword_arguments: dict[str, Any] = Field(default_factory=dict)
    related_tables: list[str] = Field(default_factory=list)
    status: Literal["ENABLED", "DISABLED"] = "ENABLED"
    description: str = ""
    server_ids: list[int] = Field(min_length=1)
    runtime: RuntimePayload
    schedule: SchedulePayload


class TaskScheduleUpdate(BaseModel):
    cron_expression: str | None = None
    timezone: str | None = None
    misfire_policy: Literal["FIRE_NOW", "FIRE_ONCE", "SKIP"] | None = None
    enabled: bool | None = None


class AgentRegisterRequest(BaseModel):
    server_code: str
    server_name: str
    server_ip: str = ""
    environment: str = "production"
    max_container_slots: int = 4
    agent_code: str
    agent_version: str = ""
    hostname: str = ""
    os_name: str = ""
    python_version: str = ""
    docker_version: str = ""
    cpu_count: int = 0
    memory_total_bytes: int = 0


class AgentRegisterResponse(BaseModel):
    agent_id: int
    server_id: int
    agent_token: str
    lease_seconds: int


class AgentHeartbeat(BaseModel):
    server_ip: str = ""
    agent_version: str = ""
    hostname: str = ""
    os_name: str = ""
    python_version: str = ""
    docker_version: str = ""
    cpu_count: int = 0
    memory_total_bytes: int = 0
    cpu_percent: Decimal = Decimal("0")
    memory_percent: Decimal = Decimal("0")
    disk_percent: Decimal = Decimal("0")
    load_1m: Decimal = Decimal("0")
    load_5m: Decimal = Decimal("0")
    network_sent_bytes: int = 0
    network_received_bytes: int = 0
    running_task_count: int = 0
    process_count: int = 0
    docker_image_bytes: int = 0
    last_error: str = ""


class ClaimRequest(BaseModel):
    limit: int = Field(default=1, ge=1, le=20)


class RunStartedRequest(BaseModel):
    container_id: str
    container_name: str


class RunHeartbeatRequest(BaseModel):
    container_id: str = ""
    status: str = "RUNNING"


class RunFinishRequest(BaseModel):
    status: Literal["SUCCESS", "FAILED", "TIMEOUT", "CANCELLED", "LOST"]
    exit_code: int | None = None
    error_type: str = ""
    error_message: str = ""
    inspect_summary: dict[str, Any] | None = None


class RunLogAppendRequest(BaseModel):
    lines: list[str] = Field(default_factory=list, max_length=500)


class ContainerEventRequest(BaseModel):
    container_id: str = ""
    container_name: str = ""
    event_type: str
    event_action: str = ""
    exit_code: int | None = None
    event_message: str = ""
