from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.utils import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", str_strip_whitespace=True)


class ORMModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class LoginRequest(ApiModel):
    user_name: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)
    force_login_token: str | None = Field(default=None, max_length=2000)


class SessionActivityUpdate(ApiModel):
    active: bool = True


class UserCreate(ApiModel):
    user_name: str = Field(min_length=2, max_length=50)
    nick_name: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=8, max_length=200)
    role_type: Literal["SUPER_ADMIN", "NORMAL_USER"] = "NORMAL_USER"
    company_id: int | None = None
    status: Literal["ENABLED", "DISABLED"] = "ENABLED"


class UserUpdate(ApiModel):
    nick_name: str | None = Field(default=None, min_length=1, max_length=50)
    role_type: Literal["SUPER_ADMIN", "NORMAL_USER"] | None = None
    company_id: int | None = None
    status: Literal["ENABLED", "DISABLED"] | None = None


class OwnPasswordUpdate(ApiModel):
    old_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)
    confirm_password: str = Field(min_length=8, max_length=200)


class UserPasswordResetCreate(ApiModel):
    new_password: str = Field(min_length=8, max_length=200)
    must_change_password: bool = True


class CompanyCreate(ApiModel):
    company_code: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=2, max_length=100)
    company_name: str = Field(min_length=1, max_length=150)
    timezone: str = Field(default="Asia/Shanghai", max_length=100)
    description: str = Field(default="", max_length=500)


class CompanyUpdate(ApiModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=150)
    timezone: str | None = Field(default=None, max_length=100)
    status: Literal["ENABLED", "DISABLED", "ARCHIVED"] | None = None
    description: str | None = Field(default=None, max_length=500)




class SystemSettingsUpdate(ApiModel):
    platform_public_url: str | None = Field(default=None, max_length=500)


class CompanyResourceConfigCreate(ApiModel):
    company_id: int
    resource_type: Literal["MYSQL_MAIN", "REDIS_CACHE", "MONGO_RAW", "OSS_MEDIA"]
    resource_name: str = Field(default="", max_length=100)
    config: dict[str, Any] = Field(default_factory=dict)


class CompanyResourceConfigTest(ApiModel):
    force_success: bool = False

class ServerCreate(ApiModel):
    company_id: int
    server_code: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=2, max_length=100)
    server_name: str = Field(min_length=1, max_length=100)
    server_ip: str = Field(default="", max_length=128)
    environment: str = Field(default="production", max_length=30)
    max_container_slots: int = Field(default=4, ge=1, le=1000)
    labels: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    registry_credential_ref: str = Field(default="", max_length=200)
    work_dir: str = Field(default="/data/crawler-agent", max_length=500)
    description: str = Field(default="", max_length=500)


class ServerUpdate(ApiModel):
    server_name: str | None = Field(default=None, min_length=1, max_length=100)
    server_ip: str | None = Field(default=None, max_length=128)
    manage_status: Literal["ENABLED", "MAINTENANCE", "DISABLED"] | None = None
    max_container_slots: int | None = Field(default=None, ge=1, le=1000)
    labels: dict[str, Any] | None = None
    capabilities: dict[str, Any] | None = None
    registry_credential_ref: str | None = Field(default=None, max_length=200)
    work_dir: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=500)


class CompanyDiscoveryManifestTask(ApiModel):
    definition_key: str = Field(min_length=1, max_length=200)
    task_name: str = Field(min_length=1, max_length=200)
    entry_module: str = Field(min_length=1, max_length=300)
    entry_function: str = Field(min_length=1, max_length=120)
    default_params: dict[str, Any] = Field(default_factory=dict)
    suggested_cron: str = Field(default="", max_length=100)
    execution_mode: Literal["SINGLE", "SHARDED"] = "SINGLE"
    idempotency_policy: Literal["IDEMPOTENT", "CHECKPOINTABLE", "MANUAL_CONFIRM", "NON_IDEMPOTENT"] = "IDEMPOTENT"
    resource_requirements: dict[str, Any] = Field(default_factory=dict)
    required_capabilities: dict[str, Any] = Field(default_factory=dict)
    platform_code: str = Field(default="", max_length=100)
    required_configs: list[dict[str, Any]] = Field(default_factory=list)
    required_credentials: list[dict[str, Any]] = Field(default_factory=list)
    output_tables: list[dict[str, Any]] = Field(default_factory=list)
    contract_version: str = Field(default="1", max_length=30)
    runtime_mode: Literal["SHARED_ENV_ISOLATED", "WORKER_POOL", "DEDICATED_CONTAINER"] = "SHARED_ENV_ISOLATED"
    task_group: str = Field(default="default", max_length=100)
    task_max_concurrency: int = Field(default=1, ge=1, le=1000)
    group_max_concurrency: int = Field(default=4, ge=1, le=1000)
    exclusive_mode: bool = False
    io_class: Literal["LOW", "NORMAL", "HIGH"] = "NORMAL"
    shm_size_mb: int = Field(default=64, ge=16, le=65536)
    log_limit_mb: int = Field(default=50, ge=1, le=10240)
    resource_locks: list[str] = Field(default_factory=list)
    secret_refs: list[Any] = Field(default_factory=list)
    allow_offline_run: bool = False
    offline_policy: dict[str, Any] = Field(default_factory=dict)
    source_file: str = Field(default="sch.py", max_length=300)
    source_fingerprint: str = Field(default="", max_length=100)


class ProjectManifest(ApiModel):
    manifest_version: str = Field(default="1", max_length=30)
    company_code: str | None = Field(default=None, max_length=100)
    project_key: str = Field(min_length=1, max_length=200)
    project_name: str = Field(min_length=1, max_length=150)
    project_code: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=2, max_length=100)
    repository_url: str = Field(default="", max_length=500)
    image_repository: str = Field(min_length=1, max_length=500)
    image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    git_branch: str = Field(default="", max_length=100)
    git_commit: str = Field(default="", max_length=100)
    release_version: str = Field(min_length=1, max_length=100)
    release_channel: str = Field(default="stable", min_length=1, max_length=50)
    runtime_type: str = Field(default="python", max_length=50)
    supported_arch: str = Field(default="", max_length=100)
    required_capabilities: dict[str, Any] = Field(default_factory=dict)
    task_definitions: list[CompanyDiscoveryManifestTask] = Field(default_factory=list)


class ProjectDiscoveryCreate(ApiModel):
    company_id: int
    server_code: str | None = Field(default=None, min_length=1, max_length=100)
    server_codes: list[str] = Field(default_factory=list)
    manifest: ProjectManifest

    @model_validator(mode="after")
    def normalize_server_codes(self) -> "ProjectDiscoveryCreate":
        seen: set[str] = set()
        items: list[str] = []
        for value in [self.server_code or "", *(self.server_codes or [])]:
            for raw in str(value or "").split(","):
                code = raw.strip()
                if code and code not in seen:
                    items.append(code)
                    seen.add(code)
        self.server_codes = items
        self.server_code = items[0] if items else None
        return self


class ProjectImport(ApiModel):
    discovered_project_id: int
    remark: str = Field(default="", max_length=500)
    dispatch_mode: Literal["PRIMARY_STANDBY", "LOAD_BALANCE"] = "LOAD_BALANCE"
    min_available_servers: int = Field(default=1, ge=1, le=100)
    max_active_servers: int = Field(default=10, ge=1, le=100)
    allow_deployed_fallback: bool = True
    allow_company_pool_fallback: bool = False
    default_runtime_mode: Literal["SHARED_ENV_ISOLATED", "WORKER_POOL", "DEDICATED_CONTAINER"] = "SHARED_ENV_ISOLATED"
    default_task_max_concurrency: int = Field(default=1, ge=1, le=1000)
    default_group_max_concurrency: int = Field(default=4, ge=1, le=1000)
    default_shm_size_mb: int = Field(default=64, ge=16, le=65536)
    default_log_limit_mb: int = Field(default=50, ge=1, le=10240)
    container_config: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(ApiModel):
    project_name: str | None = Field(default=None, min_length=1, max_length=150)
    remark: str | None = Field(default=None, max_length=500)
    status: Literal["ENABLED", "DISABLED", "ARCHIVED"] | None = None
    online_status: Literal["DRAFT", "READY", "ONLINE", "SUSPENDED", "OFFLINE"] | None = None
    dispatch_mode: Literal["PRIMARY_STANDBY", "LOAD_BALANCE"] | None = None
    min_available_servers: int | None = Field(default=None, ge=1, le=100)
    max_active_servers: int | None = Field(default=None, ge=1, le=100)
    allow_deployed_fallback: bool | None = None
    allow_company_pool_fallback: bool | None = None
    default_runtime_mode: Literal["SHARED_ENV_ISOLATED", "WORKER_POOL", "DEDICATED_CONTAINER"] | None = None
    default_task_max_concurrency: int | None = Field(default=None, ge=1, le=1000)
    default_group_max_concurrency: int | None = Field(default=None, ge=1, le=1000)
    default_shm_size_mb: int | None = Field(default=None, ge=16, le=65536)
    default_log_limit_mb: int | None = Field(default=None, ge=1, le=10240)
    container_config: dict[str, Any] | None = None
    description: str | None = Field(default=None, max_length=500)


class ProjectServerUpsert(ApiModel):
    server_id: int
    scheduling_status: Literal["ENABLED", "PAUSED", "DRAINING", "AUTO_EJECTED", "RECOVERING", "DISABLED"] = "ENABLED"
    server_role: Literal["PRIMARY", "STANDBY", "ACTIVE", "CANDIDATE", "DISABLED"] = "ACTIVE"
    priority: int = Field(default=100, ge=1, le=10000)
    weight: int = Field(default=100, ge=0, le=10000)
    max_concurrency: int = Field(default=4, ge=1, le=1000)
    auto_eject_enabled: bool = True
    auto_recover_enabled: bool = True


class ProjectServerPoolUpdate(ApiModel):
    servers: list[ProjectServerUpsert] = Field(default_factory=list)
    reason: str = Field(default="", max_length=500)


class ProjectServerPoolAnalysis(ApiModel):
    servers: list[ProjectServerUpsert] = Field(default_factory=list)


class TaskSchedulePanelQuery(ApiModel):
    company_id: int | None = None
    project_id: int | None = None
    task_name: str | None = Field(default=None, max_length=200)
    task_code: str | None = Field(default=None, max_length=120)
    entry_keyword: str | None = Field(default=None, max_length=300)
    server_id: int | None = None
    task_group: str | None = Field(default=None, max_length=100)
    task_platform: str | None = Field(default=None, max_length=150)
    task_status: str | None = Field(default=None, max_length=30)
    schedule_status: str | None = Field(default=None, max_length=30)
    last_run_status: str | None = Field(default=None, max_length=30)
    owner_user_id: int | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)


class TaskFromDefinitionCreate(ApiModel):
    definition_id: int
    owner_user_id: int | None = None
    task_code: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=2, max_length=120)
    task_name: str = Field(min_length=1, max_length=200)
    parameters: dict[str, Any] = Field(default_factory=dict)
    config_bindings: dict[str, Any] = Field(default_factory=dict)
    credential_bindings: dict[str, Any] = Field(default_factory=dict)
    status: Literal["DRAFT", "ENABLED", "PAUSED", "DISABLED"] = "DRAFT"
    image_policy: Literal["RELEASE_CHANNEL", "PINNED"] = "RELEASE_CHANNEL"
    release_channel: str = Field(default="stable", min_length=1, max_length=50)
    fixed_release_id: int | None = None
    cpu_limit: float = Field(default=1.0, gt=0, le=128)
    memory_limit_mb: int = Field(default=1024, ge=128, le=1048576)
    timeout_seconds: int = Field(default=3600, ge=1, le=604800)
    max_retry_count: int = Field(default=0, ge=0, le=20)
    schedule_status: Literal["ENABLED", "PAUSED", "DISABLED"] = "PAUSED"
    schedule_type: Literal["CRON", "MANUAL"] = "MANUAL"
    cron_expression: str = Field(default="", max_length=1000)
    schedule_timezone: str = Field(default="Asia/Shanghai", max_length=100)
    overlap_policy: Literal["SKIP", "QUEUE", "CONCURRENT", "CANCEL_OLD"] = "QUEUE"
    schedule_config: dict[str, Any] = Field(default_factory=dict)
    schedule_label: str = Field(default="", max_length=200)
    server_ids: list[int] = Field(default_factory=list)
    runtime_mode: Literal["SHARED_ENV_ISOLATED", "WORKER_POOL", "DEDICATED_CONTAINER"] | None = None
    task_group: str | None = Field(default=None, max_length=100)
    task_max_concurrency: int | None = Field(default=None, ge=1, le=1000)
    group_max_concurrency: int | None = Field(default=None, ge=1, le=1000)
    exclusive_mode: bool | None = None
    io_class: Literal["LOW", "NORMAL", "HIGH"] | None = None
    shm_size_mb: int | None = Field(default=None, ge=16, le=65536)
    log_limit_mb: int | None = Field(default=None, ge=1, le=10240)
    resource_locks: list[str] | None = None
    description: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validate_policy(self) -> "TaskFromDefinitionCreate":
        if self.image_policy == "PINNED" and not self.fixed_release_id:
            raise ValueError("fixedReleaseId is required when imagePolicy is PINNED")
        if self.schedule_type == "CRON" and not self.cron_expression and not self.schedule_config:
            raise ValueError("cronExpression or scheduleConfig is required when scheduleType is CRON")
        return self


class TaskUpdate(ApiModel):
    owner_user_id: int | None = None
    task_name: str | None = Field(default=None, min_length=1, max_length=200)
    parameters: dict[str, Any] | None = None
    config_bindings: dict[str, Any] | None = None
    credential_bindings: dict[str, Any] | None = None
    status: Literal["DRAFT", "ENABLED", "PAUSED", "DISABLED", "ARCHIVED"] | None = None
    image_policy: Literal["RELEASE_CHANNEL", "PINNED"] | None = None
    release_channel: str | None = Field(default=None, min_length=1, max_length=50)
    fixed_release_id: int | None = None
    cpu_limit: float | None = Field(default=None, gt=0, le=128)
    memory_limit_mb: int | None = Field(default=None, ge=128, le=1048576)
    timeout_seconds: int | None = Field(default=None, ge=1, le=604800)
    max_retry_count: int | None = Field(default=None, ge=0, le=20)
    runtime_mode: Literal["SHARED_ENV_ISOLATED", "WORKER_POOL", "DEDICATED_CONTAINER"] | None = None
    task_group: str | None = Field(default=None, max_length=100)
    task_max_concurrency: int | None = Field(default=None, ge=1, le=1000)
    group_max_concurrency: int | None = Field(default=None, ge=1, le=1000)
    exclusive_mode: bool | None = None
    io_class: Literal["LOW", "NORMAL", "HIGH"] | None = None
    shm_size_mb: int | None = Field(default=None, ge=16, le=65536)
    log_limit_mb: int | None = Field(default=None, ge=1, le=10240)
    resource_locks: list[str] | None = None
    description: str | None = Field(default=None, max_length=1000)


class ScheduleUpdate(ApiModel):
    schedule_status: Literal["ENABLED", "PAUSED", "DISABLED", "ERROR"] | None = None
    schedule_type: Literal["CRON", "MANUAL"] | None = None
    cron_expression: str | None = Field(default=None, max_length=1000)
    schedule_timezone: str | None = Field(default=None, max_length=100)
    overlap_policy: Literal["SKIP", "QUEUE", "CONCURRENT", "CANCEL_OLD"] | None = None
    schedule_config: dict[str, Any] | None = None
    schedule_label: str | None = Field(default=None, max_length=200)


class CronPreviewRequest(ApiModel):
    cron_expression: str | None = Field(default=None, max_length=1000)
    schedule_config: dict[str, Any] | None = None
    timezone: str = Field(default="Asia/Shanghai", max_length=100)
    count: int = Field(default=5, ge=1, le=20)


class ManualRunCreate(ApiModel):
    task_id: int
    parameters: dict[str, Any] = Field(default_factory=dict)


class AgentRegistration(ApiModel):
    company_id: int
    server_code: str = Field(min_length=2, max_length=100)
    server_name: str = Field(min_length=1, max_length=100)
    server_ip: str = Field(default="", max_length=128)
    agent_code: str = Field(min_length=2, max_length=100)
    agent_name: str = Field(default="", max_length=100)
    max_container_slots: int = Field(default=4, ge=1, le=1000)


class AgentJoinTokenCreate(ApiModel):
    company_id: int
    server_code: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=2, max_length=100)
    server_name: str = Field(min_length=1, max_length=100)
    agent_code: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=2, max_length=100)
    agent_name: str = Field(default="", max_length=100)
    max_container_slots: int = Field(default=2, ge=1, le=1000)
    work_dir: str = Field(default="/data/crawler-agent", max_length=500)
    labels: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    registry_credential_ref: str = Field(default="", max_length=200)
    install_mode: Literal["AUTO", "ROOT", "USER"] = "AUTO"
    install_target: Literal["LOCAL", "REMOTE"] = "REMOTE"
    platform_url: str = Field(default="", max_length=500)
    expires_in_hours: int = Field(default=24, ge=1, le=720)


class AgentBootstrapEnvRequest(ApiModel):
    join_token: str = Field(min_length=10, max_length=500)
    hostname: str = Field(default="", max_length=200)
    install_report: dict[str, Any] = Field(default_factory=dict)


class ProjectReleaseDeploy(ApiModel):
    release_id: int | None = None
    server_ids: list[int] = Field(default_factory=list)
    prewarm_when_idle: bool = True
    max_parallel_pulls: int = Field(default=2, ge=1, le=100)
    reason: str = Field(default="", max_length=500)


class AgentHeartbeat(ApiModel):
    agent_instance_id: str = Field(min_length=1, max_length=100)
    agent_version: str = Field(default="", max_length=50)
    protocol_version: str = Field(default="3.0", max_length=30)
    health_status: Literal["HEALTHY", "UNHEALTHY", "OFFLINE", "UNKNOWN"] | None = None
    capacity_status: Literal["NORMAL", "BUSY", "FULL", "DRAINED", "EXHAUSTED", "UNKNOWN"] | None = None
    docker_status: str = Field(default="UNKNOWN", max_length=500)
    cpu_usage: float | None = None
    memory_usage: float | None = None
    disk_usage: float | None = None
    inode_usage: float | None = None
    load_average: float | None = None
    running_containers: int = Field(default=0, ge=0)
    available_slots: int = Field(default=0, ge=0)
    max_slots: int | None = Field(default=None, ge=0)
    project_data_root_writable: bool | None = None
    docker_sock_accessible: bool | None = None
    timezone: str = Field(default="", max_length=100)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    current_runs: dict[str, Any] = Field(default_factory=dict)
    last_error: str = Field(default="", max_length=4000)


class AgentImagePullResult(ApiModel):
    project_id: int
    release_id: int | None = None
    image_repository: str = Field(default="", max_length=500)
    image_digest: str = Field(min_length=1, max_length=100)
    pull_status: Literal["READY", "FAILED"]
    message: str = Field(default="", max_length=4000)


class AgentContainerCleanupResult(ApiModel):
    cleanup_id: str = Field(min_length=1, max_length=100)
    cleanup_scope: Literal["PROJECT", "TASK"]
    project_id: int
    task_id: int | None = None
    success: bool = True
    stopped_count: int = Field(default=0, ge=0)
    removed_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    message: str = Field(default="", max_length=4000)


class AgentRunClaim(ApiModel):
    agent_instance_id: str = Field(default="", max_length=100)


class AgentRunContainerSnapshotCreate(ApiModel):
    run_id: int
    lease_token: str = Field(min_length=1, max_length=64)
    container_id: str = Field(default="", max_length=128)
    container_name: str = Field(default="", max_length=200)
    image_digest: str = Field(default="", max_length=100)
    container_status: Literal["NOT_CREATED", "PULLING_IMAGE", "CREATING", "RUNNING", "EXITED", "FAILED", "TIMED_OUT", "OOM_KILLED", "CLEANED", "LOST", "UNKNOWN"] = "UNKNOWN"
    exit_code: int | None = None
    oom_killed: bool | None = None
    restart_count: int = Field(default=0, ge=0)
    cpu_usage: float | None = None
    memory_usage_mb: float | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_log_line: str = Field(default="", max_length=1000)
    payload: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime | None = None
    agent_instance_id: str | None = Field(default=None, max_length=100)


class AgentRunHeartbeat(ApiModel):
    run_id: int
    lease_token: str = Field(min_length=1, max_length=64)
    message: str = Field(default="", max_length=4000)
    agent_instance_id: str | None = Field(default=None, max_length=100)


class AgentRunResult(ApiModel):
    run_id: int
    lease_token: str = Field(min_length=1, max_length=64)
    run_status: Literal["SUCCEEDED", "PARTIAL_SUCCESS", "FAILED", "CANCELLED", "TIMED_OUT"]
    result_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: str = Field(default="", max_length=10000)
    agent_instance_id: str | None = Field(default=None, max_length=100)


class AgentRunEventCreate(ApiModel):
    run_id: int
    lease_token: str = Field(min_length=1, max_length=64)
    event_type: str = Field(min_length=1, max_length=100)
    event_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    stage: str = Field(default="", max_length=80)
    message: str = Field(default="", max_length=4000)
    payload: dict[str, Any] = Field(default_factory=dict)
    agent_instance_id: str | None = Field(default=None, max_length=100)


class AgentRunLogChunkCreate(ApiModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", str_strip_whitespace=False)

    run_id: int
    lease_token: str = Field(min_length=1, max_length=64)
    stream: Literal["stdout", "stderr", "file"] = "stdout"
    seq: int = Field(ge=1)
    offset_start: int = Field(default=0, ge=0)
    offset_end: int = Field(default=0, ge=0)
    content: str = Field(default="", max_length=262144)
    agent_instance_id: str | None = Field(default=None, max_length=100)


class AgentRunLogFinalizeCreate(ApiModel):
    run_id: int
    lease_token: str = Field(min_length=1, max_length=64)
    log_status: Literal["COMPLETE", "FAILED", "TRUNCATED"] = "COMPLETE"
    log_path: str = Field(default="", max_length=500)
    log_truncated: bool = False
    failed_stage: str = Field(default="", max_length=80)
    error_type: str = Field(default="", max_length=100)
    error_summary: str = Field(default="", max_length=1000)
    retryable: bool | None = None
    diagnosis: dict[str, Any] = Field(default_factory=dict)
    agent_instance_id: str | None = Field(default=None, max_length=100)


class RunLogTailQuery(ApiModel):
    after_seq: int = Field(default=0, ge=0)
    limit: int = Field(default=200, ge=1, le=1000)
    keyword: str = Field(default="", max_length=200)
    stream: str = Field(default="", max_length=20)


class NotificationChannelCreate(ApiModel):
    scope_type: Literal["SYSTEM", "COMPANY", "PROJECT"] = "SYSTEM"
    company_id: int | None = None
    project_id: int | None = None
    channel_name: str = Field(min_length=1, max_length=100)
    channel_type: Literal["FEISHU", "WEWORK", "DINGTALK", "EMAIL"]
    channel_status: Literal["ENABLED", "DISABLED"] = "DISABLED"
    config: dict[str, Any] = Field(default_factory=dict)
    p0_only: bool = True
    cooldown_seconds: int = Field(default=1800, ge=60, le=86400)


class NotificationChannelUpdate(ApiModel):
    channel_name: str | None = Field(default=None, min_length=1, max_length=100)
    channel_status: Literal["ENABLED", "DISABLED", "ERROR"] | None = None
    config: dict[str, Any] | None = None
    p0_only: bool | None = None
    cooldown_seconds: int | None = Field(default=None, ge=60, le=86400)


class UserSessionRevoke(ApiModel):
    reason: str = Field(default="管理员强制下线", max_length=200)


class NotificationChannelTest(ApiModel):
    title: str = Field(default="爬虫管理平台测试通知", max_length=200)
    content: str = Field(default="这是一条 P0 告警渠道测试消息。", max_length=2000)


class AccountStatusEventCreate(ApiModel):
    company_id: int | None = None
    company_code: str | None = Field(default=None, min_length=1, max_length=100)
    platform_code: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=100)
    credential_key: str = Field(pattern=r"^[A-Za-z0-9_.:@/-]+$", min_length=1, max_length=150)
    credential_name: str = Field(default="", max_length=200)
    run_id: int | None = None
    task_id: int | None = None
    agent_code: str = Field(default="", max_length=100)
    slot: str = Field(default="", max_length=80)
    subject_type: str = Field(default="", max_length=80)
    subject_key: str = Field(default="", max_length=200)
    subject_name: str = Field(default="", max_length=300)
    affects_credential: bool = True
    event_type: Literal["STATUS", "LEASE", "MANUAL_TEST", "AGENT_PROBE", "EXPIRES_AT", "SUBJECT_BINDING"] = "STATUS"
    status_code: str = Field(pattern=r"^[A-Z0-9_.-]+$", min_length=1, max_length=80)
    severity: Literal["INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    source: Literal["TASK_RUN", "MANUAL_TEST", "AGENT_PROBE", "EXPIRES_AT", "SDK_SPOOL", "ADMIN"] = "TASK_RUN"
    message: str = Field(default="", max_length=1000)
    observed_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    event_uid: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validate_company_locator(self) -> "AccountStatusEventCreate":
        if not self.company_id and not self.company_code:
            raise ValueError("companyId 或 companyCode 至少提供一个")
        return self


class AccountCredentialEnableUpdate(ApiModel):
    enabled: bool
    reason: str = Field(default="", max_length=500)




class CredentialLeaseAcquire(ApiModel):
    company_id: int | None = None
    company_code: str | None = Field(default=None, min_length=1, max_length=100)
    platform_code: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=100)
    credential_key: str = Field(pattern=r"^[A-Za-z0-9_.:@/-]+$", min_length=1, max_length=150)
    slot: str = Field(default="", max_length=80)
    run_id: int | None = None
    task_id: int | None = None
    agent_code: str = Field(default="", max_length=100)
    lease_seconds: int = Field(default=1800, ge=60, le=86400)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_company_locator(self) -> "CredentialLeaseAcquire":
        if not self.company_id and not self.company_code:
            raise ValueError("companyId 或 companyCode 至少提供一个")
        return self


class CredentialLeaseRelease(ApiModel):
    lease_id: int | None = None
    lease_token: str | None = Field(default=None, max_length=200)
    reason: str = Field(default="completed", max_length=200)

    @model_validator(mode="after")
    def validate_locator(self) -> "CredentialLeaseRelease":
        if not self.lease_id and not self.lease_token:
            raise ValueError("leaseId 或 leaseToken 至少提供一个")
        return self


class CredentialSubjectBindingCreate(ApiModel):
    company_id: int | None = None
    company_code: str | None = Field(default=None, min_length=1, max_length=100)
    platform_code: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=100)
    subject_type: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=80)
    subject_key: str = Field(min_length=1, max_length=200)
    subject_name: str = Field(default="", max_length=300)
    credential_key: str = Field(pattern=r"^[A-Za-z0-9_.:@/-]+$", min_length=1, max_length=150)
    binding_policy: Literal["BIND_ON_SUCCESS", "MANUAL"] = "BIND_ON_SUCCESS"
    rebinding_policy: Literal["STRICT", "MANUAL_ONLY", "AUTO_ON_PERMANENT_INVALID"] = "MANUAL_ONLY"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_company_locator(self) -> "CredentialSubjectBindingCreate":
        if not self.company_id and not self.company_code:
            raise ValueError("companyId 或 companyCode 至少提供一个")
        return self


class CredentialSubjectBindingUpdate(ApiModel):
    credential_key: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.:@/-]+$", min_length=1, max_length=150)
    binding_status: Literal["ACTIVE", "SUSPENDED", "REBOUND", "RELEASED"] | None = None
    rebinding_policy: Literal["STRICT", "MANUAL_ONLY", "AUTO_ON_PERMANENT_INVALID"] | None = None
    reason: str = Field(default="", max_length=500)
    metadata: dict[str, Any] | None = None
