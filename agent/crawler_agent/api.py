from __future__ import annotations

import json
import time
from pathlib import Path
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
        self.config.spool_dir.mkdir(parents=True, exist_ok=True)

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

    def _spool(self, path: str, payload: dict[str, Any]) -> None:
        safe_name = f"{int(time.time() * 1000)}-{payload.get('runId', 'run')}-{path.strip('/').replace('/', '_')}.json"
        target = self.config.spool_dir / safe_name
        target.write_text(json.dumps({"path": path, "payload": payload}, ensure_ascii=False), encoding="utf-8")

    def flush_spool(self, limit: int = 50) -> int:
        sent = 0
        for item in sorted(self.config.spool_dir.glob("*.json"))[:limit]:
            try:
                data = json.loads(item.read_text(encoding="utf-8"))
                self._request("POST", data["path"], json=data["payload"])
                item.unlink(missing_ok=True)
                sent += 1
            except LeaseLostError:
                item.unlink(missing_ok=True)
            except Exception:
                break
        return sent

    def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._request("POST", "/agent-heartbeats", json=payload) or {}
        self.flush_spool()
        return data

    def claim(self) -> dict[str, Any] | None:
        return self._request("POST", "/agent-run-claims", json={"agentInstanceId": self.config.instance_id})

    def run_heartbeat(self, run_id: int, lease_token: str, message: str = "") -> dict[str, Any]:
        return self._request("POST", "/agent-run-heartbeats", json={"runId": run_id, "leaseToken": lease_token, "message": message, "agentInstanceId": self.config.instance_id}) or {}

    def finish(self, run_id: int, lease_token: str, status: str, result: dict[str, Any] | None = None, error: str = "") -> dict[str, Any]:
        body = {"runId": run_id, "leaseToken": lease_token, "runStatus": status, "resultPayload": result or {}, "errorMessage": error, "agentInstanceId": self.config.instance_id}
        try:
            return self._request("POST", "/agent-run-results", json=body) or {}
        except PlatformUnavailable:
            self._spool("/agent-run-results", body)
            return {"spooled": True}

    def run_event(self, run_id: int, lease_token: str, event_type: str, stage: str, message: str = "", event_level: str = "INFO", payload: dict[str, Any] | None = None) -> None:
        body = {"runId": run_id, "leaseToken": lease_token, "eventType": event_type, "eventLevel": event_level, "stage": stage, "message": message, "payload": payload or {}, "agentInstanceId": self.config.instance_id}
        try:
            self._request("POST", "/agent-run-events", json=body)
        except PlatformUnavailable:
            self._spool("/agent-run-events", body)

    def log_chunk(self, run_id: int, lease_token: str, stream: str, seq: int, offset_start: int, content: str) -> None:
        encoded_len = len(content.encode("utf-8", errors="replace"))
        body = {"runId": run_id, "leaseToken": lease_token, "stream": stream, "seq": seq, "offsetStart": offset_start, "offsetEnd": offset_start + encoded_len, "content": content, "agentInstanceId": self.config.instance_id}
        try:
            self._request("POST", "/agent-run-log-chunks", json=body)
        except PlatformUnavailable:
            self._spool("/agent-run-log-chunks", body)



    def container_snapshot(self, run_id: int, lease_token: str, **kwargs: Any) -> None:
        body = {"runId": run_id, "leaseToken": lease_token, "agentInstanceId": self.config.instance_id, **kwargs}
        try:
            self._request("POST", "/agent-container-snapshots", json=body)
        except PlatformUnavailable:
            self._spool("/agent-container-snapshots", body)
        except LeaseLostError:
            pass

    def finalize_logs(self, run_id: int, lease_token: str, status: str = "COMPLETE", **kwargs: Any) -> None:
        body = {"runId": run_id, "leaseToken": lease_token, "logStatus": status, "agentInstanceId": self.config.instance_id, **kwargs}
        try:
            self._request("POST", "/agent-run-log-finalizations", json=body)
        except PlatformUnavailable:
            self._spool("/agent-run-log-finalizations", body)

    def image_pull_result(self, project_id: int, release_id: int | None, image_repository: str, image_digest: str, pull_status: str, message: str = "") -> dict[str, Any]:
        return self._request("POST", "/agent-image-pull-results", json={
            "projectId": project_id,
            "releaseId": release_id,
            "imageRepository": image_repository,
            "imageDigest": image_digest,
            "pullStatus": pull_status,
            "message": message,
        }) or {}

    def container_cleanup_result(self, cleanup: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/agent-container-cleanup-results", json={
            "cleanupId": cleanup.get("cleanupId") or "",
            "cleanupScope": cleanup.get("cleanupScope") or "PROJECT",
            "projectId": int(cleanup.get("projectId") or 0),
            "taskId": cleanup.get("taskId"),
            "success": bool(result.get("success", True)),
            "stoppedCount": int(result.get("stoppedCount") or 0),
            "removedCount": int(result.get("removedCount") or 0),
            "failedCount": int(result.get("failedCount") or 0),
            "message": str(result.get("message") or "")[:4000],
        }) or {}

    def agent_command_result(self, command: dict[str, Any], success: bool, message: str = "", result: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", "/agent-command-results", json={
            "commandId": command.get("commandId") or "",
            "commandType": command.get("commandType") or "",
            "success": bool(success),
            "message": str(message or "")[:4000],
            "projectId": command.get("projectId"),
            "releaseId": command.get("releaseId"),
            "deploymentId": command.get("deploymentId"),
            "targetId": command.get("targetId"),
            "result": result or {},
        }) or {}
