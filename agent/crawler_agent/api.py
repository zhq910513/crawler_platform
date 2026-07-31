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

    def _request(self, method: str, path: str, **kwargs) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Agent {self.config.agent_token}"
        try:
            response = self.session.request(
                method,
                f"{self.config.platform_url}/api/v1{path}",
                headers=headers,
                timeout=self.config.request_timeout_seconds,
                verify=self.config.verify_tls,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise PlatformUnavailable(str(exc)) from exc
        if response.status_code == 401:
            raise UnauthorizedError(response.text)
        if response.status_code in {403, 404}:
            raise LeaseLostError(response.text)
        if response.status_code >= 400:
            raise PlatformUnavailable(f"HTTP {response.status_code}: {response.text[:1000]}")
        payload = response.json() if response.content else {"code": 200, "data": None}
        if payload.get("code") != 200:
            raise PlatformUnavailable(str(payload))
        return payload.get("data")

    def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/agent-heartbeats", json=payload) or {}

    def claim(self) -> dict[str, Any] | None:
        return self._request("POST", "/agent-run-claims", json={"agentInstanceId": self.config.instance_id})

    def run_heartbeat(self, run_id: int, lease_token: str, message: str = "") -> dict[str, Any]:
        return self._request("POST", "/agent-run-heartbeats", json={"runId": run_id, "leaseToken": lease_token, "message": message, "agentInstanceId": self.config.instance_id}) or {}

    def finish(self, run_id: int, lease_token: str, status: str, result: dict[str, Any] | None = None, error: str = "") -> dict[str, Any]:
        return self._request("POST", "/agent-run-results", json={"runId": run_id, "leaseToken": lease_token, "runStatus": status, "resultPayload": result or {}, "errorMessage": error, "agentInstanceId": self.config.instance_id}) or {}
