from __future__ import annotations

import json
import os
import socket
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env_or(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _json_env(name: str, default):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    value = json.loads(raw)
    return value


@dataclass(frozen=True)
class AgentConfig:
    platform_url: str = os.getenv("PLATFORM_URL", "http://127.0.0.1:8000").rstrip("/")
    bootstrap_token: str = os.getenv("AGENT_BOOTSTRAP_TOKEN", "change-this-agent-bootstrap-token")
    company_id: int = int(os.getenv("AGENT_COMPANY_ID", "0") or "0")
    agent_code: str = os.getenv("AGENT_CODE", socket.gethostname())
    server_code: str = os.getenv("SERVER_CODE", socket.gethostname())
    server_name: str = os.getenv("SERVER_NAME", socket.gethostname())
    agent_version: str = os.getenv("AGENT_VERSION", "2.0.0")
    instance_id: str = _env_or("AGENT_INSTANCE_ID", str(uuid.uuid4()))
    max_slots: int = int(os.getenv("AGENT_MAX_SLOTS", "4"))
    heartbeat_seconds: int = int(os.getenv("AGENT_HEARTBEAT_SECONDS", "15"))
    claim_seconds: int = int(os.getenv("AGENT_CLAIM_SECONDS", "3"))
    run_heartbeat_seconds: int = int(os.getenv("AGENT_RUN_HEARTBEAT_SECONDS", "10"))
    request_timeout_seconds: int = int(os.getenv("AGENT_REQUEST_TIMEOUT_SECONDS", "15"))
    verify_tls: bool = _bool_env("PLATFORM_VERIFY_TLS", True)
    allow_insecure_http: bool = _bool_env("AGENT_ALLOW_INSECURE_HTTP", False)
    run_root: Path = Path(os.getenv("AGENT_RUN_ROOT", "/var/lib/crawler-agent/runs"))
    log_upload_batch_size: int = int(os.getenv("AGENT_LOG_UPLOAD_BATCH_SIZE", "200"))
    event_upload_batch_size: int = int(os.getenv("AGENT_EVENT_UPLOAD_BATCH_SIZE", "100"))
    recovery_scan_seconds: int = int(os.getenv("AGENT_RECOVERY_SCAN_SECONDS", "10"))
    completed_retention_hours: int = int(os.getenv("AGENT_COMPLETED_RETENTION_HOURS", "72"))
    container_uid: int = int(os.getenv("CRAWLER_CONTAINER_UID", "10001"))
    container_gid: int = int(os.getenv("CRAWLER_CONTAINER_GID", "10001"))
    container_network: str = os.getenv("AGENT_CONTAINER_NETWORK", "bridge")
    registry_username: str = os.getenv("DOCKER_REGISTRY_USERNAME", "")
    registry_password: str = os.getenv("DOCKER_REGISTRY_PASSWORD", "")
    capabilities: list[str] = field(default_factory=lambda: _json_env("AGENT_CAPABILITIES", ["api", "browser"]))
    labels: dict[str, str] = field(default_factory=lambda: _json_env("AGENT_LABELS", {}))

    def validate(self) -> None:
        failures: list[str] = []
        lowered_token = self.bootstrap_token.lower()
        if len(self.bootstrap_token) < 24 or "replacewith" in lowered_token or "change-this" in lowered_token:
            failures.append("AGENT_BOOTSTRAP_TOKEN")
        if not self.platform_url.startswith(("http://", "https://")):
            failures.append("PLATFORM_URL")
        if self.platform_url.startswith("http://") and not self.allow_insecure_http:
            failures.append("PLATFORM_URL must use HTTPS or AGENT_ALLOW_INSECURE_HTTP=true")
        if self.max_slots < 1:
            failures.append("AGENT_MAX_SLOTS")
        if self.heartbeat_seconds < 3 or self.run_heartbeat_seconds < 3:
            failures.append("heartbeat interval")
        if not self.run_root.is_absolute():
            failures.append("AGENT_RUN_ROOT")
        if failures:
            raise RuntimeError("invalid agent configuration: " + ", ".join(failures))


config = AgentConfig()
