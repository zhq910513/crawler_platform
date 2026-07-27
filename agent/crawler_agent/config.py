from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class AgentConfig:
    platform_url: str = os.getenv("PLATFORM_URL", "http://127.0.0.1:8080").rstrip("/")
    bootstrap_token: str = os.getenv("AGENT_BOOTSTRAP_TOKEN", "")
    server_code: str = os.getenv("SERVER_CODE", socket.gethostname())
    server_name: str = os.getenv("SERVER_NAME", socket.gethostname())
    server_ip: str = os.getenv("SERVER_IP", "")
    environment: str = os.getenv("SERVER_ENVIRONMENT", "production")
    max_slots: int = env_int("MAX_CONTAINER_SLOTS", 4)
    poll_seconds: int = env_int("AGENT_POLL_SECONDS", 3)
    heartbeat_seconds: int = env_int("AGENT_HEARTBEAT_SECONDS", 15)
    request_timeout_seconds: int = env_int("AGENT_REQUEST_TIMEOUT_SECONDS", 30)
    state_file: Path = Path(os.getenv("AGENT_STATE_FILE", "/var/lib/crawler-agent/state.json"))
    disk_path: str = os.getenv("AGENT_DISK_PATH", "/")
    docker_registry_username: str = os.getenv("DOCKER_REGISTRY_USERNAME", "")
    docker_registry_password: str = os.getenv("DOCKER_REGISTRY_PASSWORD", "")
    docker_registry: str = os.getenv("DOCKER_REGISTRY", "")
    verify_tls: bool = os.getenv("PLATFORM_VERIFY_TLS", "true").lower() not in {"0", "false", "no"}


config = AgentConfig()
