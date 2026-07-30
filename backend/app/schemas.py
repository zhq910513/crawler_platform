from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginRequest(StrictModel):
    user_name: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class UserInfo(ORMModel):
    user_id: int
    user_name: str
    nick_name: str
    role_type: str
    status: bool


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class UserCreate(StrictModel):
    user_name: str = Field(min_length=2, max_length=50)
    nick_name: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=8, max_length=200)
    role_type: Literal["SUPER_ADMIN", "NORMAL_USER"] = "NORMAL_USER"
    status: bool = True


class UserUpdate(StrictModel):
    nick_name: str | None = Field(default=None, min_length=1, max_length=50)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    role_type: Literal["SUPER_ADMIN", "NORMAL_USER"] | None = None
    status: bool | None = None


class CompanyCreate(StrictModel):
    company_code: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=2, max_length=100)
    company_name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=500)


class CompanyMemberUpsert(StrictModel):
    user_id: int
    role: Literal["OWNER", "ADMIN", "MEMBER"]


class ProjectCreate(StrictModel):
    company_id: int
    project_code: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=2, max_length=100)
    project_name: str = Field(min_length=1, max_length=150)
    registry: str = Field(default="", max_length=255)
    repository: str = Field(default="", max_length=255)
    default_branch: str = Field(default="main", max_length=100)
    status: Literal["ENABLED", "DISABLED"] = "ENABLED"
    deployment_mode: Literal["BOOTSTRAP", "MANUAL"] = "BOOTSTRAP"
    online_status: Literal["DRAFT", "ONLINE", "OFFLINE"] = "DRAFT"
    min_agent_version: str = Field(default="2.0.0", max_length=50)
    description: str = Field(default="", max_length=500)


class ProjectMemberUpsert(StrictModel):
    user_id: int
    role: Literal["OWNER", "OPERATOR", "VIEWER"]


class RuntimePayload(StrictModel):
    image_policy: Literal["PINNED", "RELEASE_CHANNEL"] = "RELEASE_CHANNEL"
    fixed_spider_release_id: int | None = None
    release_channel: str = Field(default="stable", min_length=1, max_length=50)
    pull_policy: Literal["ALWAYS", "IF_NOT_PRESENT", "NEVER"] = "IF_NOT_PRESENT"
    cpu_limit: float = Field(default=2.0, gt=0, le=128)
    memory_limit_mb: int = Field(default=4096, ge=128, le=1048576)
    shm_size_mb: int = Field(default=256, ge=16, le=65536)
    pids_limit: int = Field(default=512, ge=16, le=65536)
    stop_grace_seconds: int = Field(default=30, ge=1, le=600)
    auto_remove: bool = True
    keep_failed_container: bool = False

    @model_validator(mode="after")
    def validate_policy(self) -> "RuntimePayload":
        if self.image_policy == "PINNED" and not self.fixed_spider_release_id:
            raise ValueError("PINNED requires fixed_spider_release_id")
        return self


class SchedulePayload(StrictModel):
    schedule_type: Literal["CRON", "MANUAL"] = "CRON"
    cron_expression: str = Field(default="", max_length=100)
    timezone: str = Field(default="Asia/Shanghai", max_length=100)
    misfire_policy: Literal["FIRE_ONCE", "SKIP"] = "FIRE_ONCE"
    max_concurrency: int = Field(default=1, ge=1, le=100)
    overlap_policy: Literal["SKIP", "QUEUE"] = "SKIP"
    timeout_seconds: int = Field(default=3600, ge=1, le=604800)
    max_retry_count: int = Field(default=0, ge=0, le=20)
    retry_interval_seconds: int = Field(default=60, ge=1, le=86400)
    retry_backoff: Literal["FIXED", "EXPONENTIAL"] = "FIXED"
    enabled: bool = True

    @model_validator(mode="after")
    def validate_cron(self) -> "SchedulePayload":
        if self.schedule_type == "CRON" and not self.cron_expression:
            raise ValueError("CRON requires cron_expression")
        return self


class TaskCreate(StrictModel):
    task_code: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=2, max_length=120)
    task_name: str = Field(min_length=1, max_length=200)
    project_id: int
    spider_task_name: str = Field(pattern=r"^[a-z0-9_]+(?:\.[a-z0-9_]+)+$", min_length=3, max_length=200)
    platform: str = Field(default="", max_length=100)
    task_group: str = Field(default="default", max_length=100)
    developer: str = Field(default="", max_length=100)
    entry_module: str = Field(default="", max_length=300)
    entry_function: str = Field(default="", max_length=120)
    source_type: Literal["MANUAL", "SCH_IMPORT", "PROJECT_MANIFEST", "CICD_IMPORT"] = "MANUAL"
    source_file: str = Field(default="", max_length=300)
    source_fingerprint: str = Field(default="", max_length=100)
    resource_requirements: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: Literal["ENABLED", "DISABLED"] = "ENABLED"
    description: str = Field(default="", max_length=1000)
    runtime: RuntimePayload = Field(default_factory=RuntimePayload)
    schedule: SchedulePayload = Field(default_factory=lambda: SchedulePayload(schedule_type="MANUAL", enabled=False))
    server_ids: list[int] = Field(default_factory=list, max_length=100)


class TaskScheduleUpdate(StrictModel):
    cron_expression: str | None = Field(default=None, max_length=100)
    timezone: str | None = Field(default=None, max_length=100)
    misfire_policy: Literal["FIRE_ONCE", "SKIP"] | None = None
    max_concurrency: int | None = Field(default=None, ge=1, le=100)
    overlap_policy: Literal["SKIP", "QUEUE"] | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=604800)
    max_retry_count: int | None = Field(default=None, ge=0, le=20)
    retry_interval_seconds: int | None = Field(default=None, ge=1, le=86400)
    retry_backoff: Literal["FIXED", "EXPONENTIAL"] | None = None
    enabled: bool | None = None


class SpiderReleaseImport(StrictModel):
    image_repository: str = Field(min_length=1, max_length=500)
    image_tag: str = Field(default="", max_length=255)
    image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    git_commit: str = Field(default="", max_length=100)
    manifest: dict[str, Any]


class ReleaseChannelUpdate(StrictModel):
    spider_release_id: int


class ProjectBootstrapTokenCreate(StrictModel):
    token_name: str = Field(default="default", min_length=1, max_length=120)
    allowed_repo: str = Field(default="", max_length=500)
    expires_in_days: int | None = Field(default=30, ge=1, le=3650)


class BootstrapPreflightReport(StrictModel):
    server_code: str = Field(default="", max_length=100)
    agent_code: str = Field(default="", max_length=100)
    status: Literal["PASS", "WARN", "FAIL"]
    stage: str = Field(default="PREFLIGHT", max_length=50)
    message: str = Field(default="", max_length=4000)
    git_branch: str = Field(default="", max_length=100)
    git_commit: str = Field(default="", max_length=100)
    checks: dict[str, Any] = Field(default_factory=dict)


class BootstrapReleaseImport(SpiderReleaseImport):
    git_branch: str = Field(default="", max_length=100)
    server_code: str = Field(default="", max_length=100)
    agent_code: str = Field(default="", max_length=100)
    project_manifest: dict[str, Any] = Field(default_factory=dict)
    preflight: dict[str, Any] = Field(default_factory=dict)
    import_entries: bool = True



class ResourceSecretCreate(StrictModel):
    company_id: int
    project_id: int | None = None
    secret_code: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=100)
    secret_name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=20000)
    description: str = Field(default="", max_length=500)
    enabled: bool = True


class ResourceConnectionCreate(StrictModel):
    company_id: int
    project_id: int | None = None
    connection_code: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=100)
    connection_name: str = Field(min_length=1, max_length=150)
    resource_type: Literal["MYSQL", "MONGO", "REDIS"]
    config: dict[str, Any]
    enabled: bool = True


class ResourceDatabaseCreate(StrictModel):
    connection_id: int
    database_code: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=100)
    database_name: str = Field(min_length=1, max_length=200)
    config: dict[str, Any] = Field(default_factory=dict)


class ResourceObjectCreate(StrictModel):
    database_id: int
    object_code: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=120)
    object_name: str = Field(min_length=1, max_length=200)
    object_type: Literal["TABLE", "COLLECTION"]


class ProjectResourceBindingUpsert(StrictModel):
    logical_name: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=200)
    resource_kind: Literal["CONNECTION", "DATABASE", "OBJECT"]
    connection_id: int | None = None
    database_id: int | None = None
    object_id: int | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "ProjectResourceBindingUpsert":
        target_map = {
            "CONNECTION": self.connection_id,
            "DATABASE": self.database_id,
            "OBJECT": self.object_id,
        }
        selected = [name for name, value in target_map.items() if value is not None]
        if selected != [self.resource_kind]:
            raise ValueError(f"{self.resource_kind} binding requires exactly one matching id")
        return self


class ProjectSecretBindingUpsert(StrictModel):
    logical_name: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=200)
    secret_id: int


class AgentRegisterRequest(StrictModel):
    protocol_version: Literal["2.0"] = "2.0"
    instance_id: str = Field(min_length=1, max_length=100)
    agent_code: str = Field(min_length=1, max_length=100)
    server_code: str = Field(min_length=1, max_length=100)
    server_name: str = Field(min_length=1, max_length=100)
    hostname: str = Field(default="", max_length=255)
    agent_version: str = Field(default="", max_length=50)
    os_name: str = Field(default="", max_length=255)
    python_version: str = Field(default="", max_length=100)
    docker_version: str = Field(default="", max_length=100)
    cpu_count: int = Field(default=0, ge=0)
    memory_total_bytes: int = Field(default=0, ge=0)
    capabilities: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    max_container_slots: int = Field(default=4, ge=1, le=1000)


class AgentRegisterResponse(BaseModel):
    agent_id: int
    server_id: int
    agent_token: str
    protocol_version: str = "2.0"
    lease_seconds: int


class AgentHeartbeat(StrictModel):
    instance_id: str
    status: Literal["ONLINE", "DEGRADED"] = "ONLINE"
    cpu_percent: float = Field(default=0, ge=0, le=100)
    memory_percent: float = Field(default=0, ge=0, le=100)
    disk_percent: float = Field(default=0, ge=0, le=100)
    load_1m: float = Field(default=0, ge=0)
    load_5m: float = Field(default=0, ge=0)
    network_sent_bytes: int = Field(default=0, ge=0)
    network_received_bytes: int = Field(default=0, ge=0)
    running_task_count: int = Field(default=0, ge=0)
    process_count: int = Field(default=0, ge=0)
    docker_image_bytes: int = Field(default=0, ge=0)
    available_slots: int = Field(default=0, ge=0)
    last_error: str = Field(default="", max_length=4000)


class ClaimRequest(StrictModel):
    available_slots: int = Field(default=1, ge=0, le=1000)


class RunStartingRequest(StrictModel):
    message: str = Field(default="", max_length=1000)


class RunStartedRequest(StrictModel):
    container_id: str = Field(min_length=1, max_length=100)
    container_name: str = Field(min_length=1, max_length=255)


class RunHeartbeatRequest(StrictModel):
    container_id: str = Field(default="", max_length=100)


class LogBatchRequest(StrictModel):
    stream: Literal["stdout", "stderr"]
    start_seq: PositiveInt
    lines: list[str] = Field(min_length=1, max_length=1000)


class RunEventItem(StrictModel):
    event_uid: str = Field(min_length=1, max_length=100)
    stream: Literal["stdout", "stderr", "agent"] = "stdout"
    seq: int | None = Field(default=None, ge=1)
    level: str = Field(default="INFO", max_length=20)
    event_name: str = Field(default="", max_length=100)
    message: str = Field(default="", max_length=10000)
    error_code: str = Field(default="", max_length=200)
    error_type: str = Field(default="", max_length=200)
    retryable: bool = False
    context: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None


class RunEventBatchRequest(StrictModel):
    events: list[RunEventItem] = Field(min_length=1, max_length=500)


class ContainerEventRequest(StrictModel):
    container_id: str = Field(default="", max_length=100)
    container_name: str = Field(default="", max_length=255)
    event_type: str = Field(min_length=1, max_length=50)
    event_action: str = Field(default="", max_length=50)
    exit_code: int | None = None
    event_message: str = Field(default="", max_length=10000)


class RunFinishRequest(StrictModel):
    status: Literal["SUCCEEDED", "PARTIAL_SUCCESS", "SKIPPED", "FAILED", "CANCELLED", "TIMED_OUT"]
    exit_code: int | None = None
    oom_killed: bool = False
    result: dict[str, Any] | None = None
    last_error: dict[str, Any] | None = None
    terminal_error: dict[str, Any] | None = None
    inspect_summary: dict[str, Any] | None = None
