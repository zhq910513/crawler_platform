from __future__ import annotations

import json
import socket
import uuid
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AGENT_", extra="ignore")

    platform_url: str = Field(default="http://api:8000")
    agent_token: str = Field(default="")
    agent_code: str = Field(default="")
    server_code: str = Field(default="")
    agent_version: str = Field(default="1.0.1")
    protocol_version: str = Field(default="1.0")
    instance_id: str = Field(default_factory=lambda: f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}")
    max_slots: int = Field(default=2, ge=1, le=100)
    poll_interval_seconds: int = Field(default=5, ge=1, le=300)
    heartbeat_interval_seconds: int = Field(default=10, ge=1, le=300)
    request_timeout_seconds: int = Field(default=20, ge=1, le=300)
    verify_tls: bool = Field(default=True)
    run_root: Path = Field(default=Path("/data/crawler-agent/runs"))
    project_data_root: Path = Field(default=Path("/data/crawler-platform/projects"))
    registry_username: str = Field(default="")
    registry_password: str = Field(default="")
    default_timeout_seconds: int = Field(default=3600, ge=1, le=604800)
    capabilities_json: str = Field(default="{}")
    docker_network: str = Field(default="")
    default_shm_size_mb: int = Field(default=64, ge=16, le=65536)
    pids_limit: int = Field(default=1024, ge=64, le=1048576)
    read_only_rootfs: bool = Field(default=False)
    log_max_file: int = Field(default=3, ge=1, le=20)
    container_user: str = Field(default="")
    enable_shared_project_cache: bool = Field(default=True)

    def capabilities(self) -> dict:
        if not self.capabilities_json.strip():
            return {}
        try:
            value = json.loads(self.capabilities_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("AGENT_CAPABILITIES_JSON 必须是合法 JSON 对象") from exc
        if not isinstance(value, dict):
            raise RuntimeError("AGENT_CAPABILITIES_JSON 必须是 JSON 对象，例如 {\"browser\": true}")
        return value

    def validate_runtime(self) -> None:
        if not self.platform_url:
            raise RuntimeError("AGENT_PLATFORM_URL is required")
        if not self.agent_token:
            raise RuntimeError("AGENT_AGENT_TOKEN is required")


config = AgentConfig()
