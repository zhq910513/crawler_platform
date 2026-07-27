from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

from crawler_agent.config import AgentConfig


class PlatformAPI:
    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.agent_token = ""
        self.agent_id: int | None = None
        self.server_id: int | None = None
        self._load_state()

    def _load_state(self) -> None:
        try:
            data = json.loads(self.config.state_file.read_text(encoding="utf-8"))
            self.agent_token = str(data.get("agent_token", ""))
            self.agent_id = data.get("agent_id")
            self.server_id = data.get("server_id")
        except Exception:
            return

    def _save_state(self) -> None:
        self.config.state_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.config.state_file.with_suffix(".tmp")
        temp.write_text(
            json.dumps(
                {"agent_token": self.agent_token, "agent_id": self.agent_id, "server_id": self.server_id},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        os.chmod(temp, 0o600)
        temp.replace(self.config.state_file)

    def register(self, payload: dict[str, Any]) -> None:
        if not self.config.bootstrap_token:
            raise RuntimeError("AGENT_BOOTSTRAP_TOKEN 未配置")
        response = self.session.post(
            f"{self.config.platform_url}/api/agent/register",
            json=payload,
            headers={"X-Agent-Bootstrap-Token": self.config.bootstrap_token},
            timeout=self.config.request_timeout_seconds,
            verify=self.config.verify_tls,
        )
        response.raise_for_status()
        data = response.json()
        self.agent_token = data["agent_token"]
        self.agent_id = data["agent_id"]
        self.server_id = data["server_id"]
        self._save_state()

    def request(self, method: str, path: str, *, json_data: dict[str, Any] | None = None, retries: int = 3) -> Any:
        if not self.agent_token:
            raise RuntimeError("Agent 尚未注册")
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                response = self.session.request(
                    method,
                    f"{self.config.platform_url}{path}",
                    json=json_data,
                    headers={"Authorization": f"Agent {self.agent_token}"},
                    timeout=self.config.request_timeout_seconds,
                    verify=self.config.verify_tls,
                )
                if response.status_code == 401:
                    raise PermissionError("Agent Token 已失效，需要重新注册")
                response.raise_for_status()
                if not response.content:
                    return None
                return response.json()
            except PermissionError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt + 1 < retries:
                    time.sleep(min(2 ** attempt, 5))
        raise RuntimeError(f"平台请求失败：{method} {path}: {last_error}") from last_error

    def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/api/agent/heartbeat", json_data=payload)

    def claim(self, limit: int) -> list[dict[str, Any]]:
        data = self.request("POST", "/api/agent/claim", json_data={"limit": limit})
        return data.get("items", [])

    def started(self, run_id: int, container_id: str, container_name: str) -> None:
        self.request("POST", f"/api/agent/runs/{run_id}/started", json_data={"container_id": container_id, "container_name": container_name})

    def run_heartbeat(self, run_id: int, container_id: str) -> dict[str, Any]:
        return self.request("POST", f"/api/agent/runs/{run_id}/heartbeat", json_data={"container_id": container_id, "status": "RUNNING"})

    def control(self, run_id: int) -> dict[str, Any]:
        return self.request("GET", f"/api/agent/runs/{run_id}/control")

    def finish(self, run_id: int, payload: dict[str, Any]) -> None:
        self.request("POST", f"/api/agent/runs/{run_id}/finish", json_data=payload, retries=5)

    def logs(self, run_id: int, lines: list[str]) -> None:
        if lines:
            self.request("POST", f"/api/agent/runs/{run_id}/logs", json_data={"lines": lines}, retries=5)

    def event(self, run_id: int, payload: dict[str, Any]) -> None:
        try:
            self.request("POST", f"/api/agent/runs/{run_id}/events", json_data=payload)
        except Exception as exc:
            print(f"上报容器事件失败 run={run_id}: {exc}")
