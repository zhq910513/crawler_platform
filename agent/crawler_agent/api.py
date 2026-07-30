from __future__ import annotations

from typing import Any

import requests

from crawler_agent.config import AgentConfig


class PlatformUnavailable(RuntimeError):
    pass


class UnauthorizedError(RuntimeError):
    pass


class LeaseLostError(RuntimeError):
    pass


class PlatformAPI:
    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.agent_token = ""
        self.agent_id: int | None = None
        self.server_id: int | None = None
        self.lease_seconds = 90

    def _request(self, method: str, path: str, *, lease_token: str | None = None, **kwargs) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        if path.endswith("/register"):
            headers["X-Agent-Bootstrap-Token"] = self.config.bootstrap_token
        elif self.agent_token:
            headers["Authorization"] = f"Agent {self.agent_token}"
        if lease_token:
            headers["X-Run-Lease-Token"] = lease_token
        try:
            response = self.session.request(
                method,
                f"{self.config.platform_url}/api/agent/v2{path}",
                headers=headers,
                timeout=self.config.request_timeout_seconds,
                verify=self.config.verify_tls,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise PlatformUnavailable(str(exc)) from exc
        if response.status_code == 401:
            raise UnauthorizedError(response.text)
        if response.status_code in {404, 409} and lease_token:
            raise LeaseLostError(response.text)
        if response.status_code >= 400:
            raise PlatformUnavailable(f"HTTP {response.status_code}: {response.text[:1000]}")
        return response.json() if response.content else {}

    def register(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._request("POST", "/register", json=payload)
        self.agent_token = data["agent_token"]
        self.agent_id = int(data["agent_id"])
        self.server_id = int(data["server_id"])
        self.lease_seconds = int(data.get("lease_seconds", 90))
        return data

    def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/heartbeat", json=payload)

    def claim(self, available_slots: int) -> list[dict[str, Any]]:
        return self._request("POST", "/claim", json={"available_slots": available_slots}).get("items", [])

    def starting(self, run_id: int, lease: str, message: str = "") -> dict[str, Any]:
        return self._request("POST", f"/runs/{run_id}/starting", lease_token=lease, json={"message": message})

    def started(self, run_id: int, lease: str, container_id: str, container_name: str) -> dict[str, Any]:
        return self._request("POST", f"/runs/{run_id}/started", lease_token=lease, json={"container_id": container_id, "container_name": container_name})

    def run_heartbeat(self, run_id: int, lease: str, container_id: str = "") -> dict[str, Any]:
        return self._request("POST", f"/runs/{run_id}/heartbeat", lease_token=lease, json={"container_id": container_id})

    def control(self, run_id: int, lease: str) -> dict[str, Any]:
        return self._request("GET", f"/runs/{run_id}/control", lease_token=lease)

    def logs(self, run_id: int, lease: str, stream: str, start_seq: int, lines: list[str]) -> dict[str, Any]:
        return self._request("POST", f"/runs/{run_id}/logs", lease_token=lease, json={"stream": stream, "start_seq": start_seq, "lines": lines})

    def events(self, run_id: int, lease: str, events: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request("POST", f"/runs/{run_id}/events", lease_token=lease, json={"events": events})

    def container_event(self, run_id: int, lease: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/runs/{run_id}/container-events", lease_token=lease, json=payload)

    def finish(self, run_id: int, lease: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/runs/{run_id}/finish", lease_token=lease, json=payload)
