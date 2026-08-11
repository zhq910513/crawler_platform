from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CrawlerProjectDeployment, CrawlerProjectDeploymentTarget, CrawlerProjectServer, CrawlerServer
from app.utils import utcnow

PENDING_KEY = "pendingAgentCommands"
RESULT_KEY = "agentCommandResults"


class AgentCommandService:
    """Store small, idempotent Agent operations in crawler_server.metrics.

    This release deliberately keeps using the existing server metrics command queue. Existing customers
    already rely on crawler_server.metrics for server-side operational state;
    using it here keeps the deployment path lightweight and migration-free.
    """

    def __init__(self, db: Session):
        self.db = db

    def enqueue_project_deploy_prepare(
        self,
        *,
        server: CrawlerServer,
        project_id: int,
        project_code: str,
        release_id: int,
        release_version: str,
        image_repository: str,
        image_digest: str,
        deployment_id: int,
        target_id: int,
        desired_scheduling_status: str = "ENABLED",
        reason: str = "",
    ) -> dict[str, Any]:
        command_id = f"project-deploy-{deployment_id}-{target_id}"
        command = {
            "commandId": command_id,
            "commandType": "PROJECT_DEPLOY_PREPARE",
            "status": "PENDING",
            "companyId": server.company_id,
            "serverId": server.server_id,
            "projectId": project_id,
            "projectCode": project_code,
            "releaseId": release_id,
            "releaseVersion": release_version,
            "deploymentId": deployment_id,
            "targetId": target_id,
            "desiredSchedulingStatus": desired_scheduling_status,
            "reason": reason,
            "createdAt": utcnow().isoformat(),
            "expiresAt": (utcnow() + timedelta(hours=24)).isoformat(),
            "payload": {
                "projectId": project_id,
                "projectCode": project_code,
                "releaseId": release_id,
                "releaseVersion": release_version,
                "deploymentId": deployment_id,
                "targetId": target_id,
                "imageRepository": image_repository,
                "imageDigest": image_digest,
                "smokeTest": True,
            },
        }
        metrics = dict(server.metrics or {})
        pending = [item for item in metrics.get(PENDING_KEY, []) if isinstance(item, dict) and item.get("commandId") != command_id]
        pending.append(command)
        metrics[PENDING_KEY] = pending[-100:]
        server.metrics = metrics
        return command

    def pending_for_server(self, server: CrawlerServer, limit: int = 20) -> list[dict[str, Any]]:
        metrics = dict(server.metrics or {})
        result: list[dict[str, Any]] = []
        now = utcnow()
        for item in metrics.get(PENDING_KEY, []) or []:
            if not isinstance(item, dict):
                continue
            if item.get("status") != "PENDING":
                continue
            expires_at = str(item.get("expiresAt") or "")
            if expires_at:
                try:
                    from datetime import datetime
                    if datetime.fromisoformat(expires_at) < now:
                        continue
                except ValueError:
                    pass
            result.append(item)
            if len(result) >= limit:
                break
        return result

    def acknowledge(self, server: CrawlerServer, result: dict[str, Any]) -> dict[str, Any]:
        command_id = str(result.get("commandId") or result.get("command_id") or "").strip()
        if not command_id:
            return {"accepted": False, "reason": "missing commandId"}
        metrics = dict(server.metrics or {})
        pending = list(metrics.get(PENDING_KEY, []) or [])
        command: dict[str, Any] | None = None
        kept: list[dict[str, Any]] = []
        for item in pending:
            if not isinstance(item, dict):
                continue
            if item.get("commandId") == command_id:
                command = item
            else:
                kept.append(item)
        if not command:
            return {"accepted": False, "reason": "command not found or already acknowledged"}
        stored = {
            "commandId": command_id,
            "commandType": command.get("commandType") or result.get("commandType") or "",
            "status": "SUCCEEDED" if result.get("success") else "FAILED",
            "success": bool(result.get("success")),
            "message": str(result.get("message") or "")[:4000],
            "projectId": command.get("projectId"),
            "releaseId": command.get("releaseId"),
            "deploymentId": command.get("deploymentId"),
            "targetId": command.get("targetId"),
            "serverId": server.server_id,
            "finishedAt": utcnow().isoformat(),
            "result": result.get("result") or {},
        }
        results = list(metrics.get(RESULT_KEY, []) or [])
        results = [item for item in results if isinstance(item, dict) and item.get("commandId") != command_id]
        results.append(stored)
        metrics[PENDING_KEY] = kept[-100:]
        metrics[RESULT_KEY] = results[-100:]
        server.metrics = metrics
        return {"accepted": True, "command": command, "stored": stored}

    def apply_project_deploy_result(self, server: CrawlerServer, ack: dict[str, Any]) -> None:
        if not ack.get("accepted"):
            return
        command = ack.get("command") or {}
        stored = ack.get("stored") or {}
        if command.get("commandType") != "PROJECT_DEPLOY_PREPARE":
            return
        project_id = int(command.get("projectId") or 0)
        release_id = int(command.get("releaseId") or 0)
        deployment_id = int(command.get("deploymentId") or 0)
        target_id = int(command.get("targetId") or 0)
        success = bool(stored.get("success"))
        message = str(stored.get("message") or "")[:4000]
        ps = self.db.scalar(select(CrawlerProjectServer).where(CrawlerProjectServer.project_id == project_id, CrawlerProjectServer.server_id == server.server_id))
        target = self.db.get(CrawlerProjectDeploymentTarget, target_id) if target_id else None
        deployment = self.db.get(CrawlerProjectDeployment, deployment_id) if deployment_id else None
        now = utcnow()
        if ps:
            ps.latest_release_id = release_id or ps.latest_release_id
            if success:
                ps.deployment_status = "DEPLOYED"
                ps.image_readiness_status = "READY"
                desired = str(command.get("desiredSchedulingStatus") or "ENABLED")
                ps.scheduling_status = desired if desired in {"ENABLED", "RECOVERING", "PAUSED", "DRAINING", "DISABLED"} else "ENABLED"
                ps.disabled_reason = ""
            else:
                ps.deployment_status = "FAILED"
                ps.image_readiness_status = "FAILED"
                ps.scheduling_status = "PAUSED"
                ps.disabled_reason = (message or "Agent 项目部署预检失败")[:500]
            ps.last_deployed_at = now
        if target:
            target.target_status = "DEPLOYED" if success else "FAILED"
            target.image_readiness_status = "READY" if success else "FAILED"
            target.last_error = "" if success else message
            target.last_deployed_at = now
        if deployment:
            self._update_deployment_strategy(deployment, target_id, stored)
            targets = list(self.db.scalars(select(CrawlerProjectDeploymentTarget).where(CrawlerProjectDeploymentTarget.deployment_id == deployment.deployment_id)).all())
            statuses = {item.target_status for item in targets}
            if targets and statuses <= {"DEPLOYED"}:
                deployment.deployment_status = "DEPLOYED"
            elif "FAILED" in statuses and not (statuses & {"PENDING_AGENT", "DISPATCHED", "DEPLOYING"}):
                deployment.deployment_status = "FAILED"
            else:
                deployment.deployment_status = "DEPLOYING"

    @staticmethod
    def _update_deployment_strategy(deployment: CrawlerProjectDeployment, target_id: int, stored: dict[str, Any]) -> None:
        strategy = dict(deployment.strategy or {})
        targets = strategy.get("targets") if isinstance(strategy.get("targets"), list) else []
        for item in targets:
            if isinstance(item, dict) and int(item.get("targetId") or 0) == int(target_id or 0):
                item["status"] = "DEPLOYED" if stored.get("success") else "FAILED"
                item["message"] = stored.get("message") or ""
                item["finishedAt"] = stored.get("finishedAt") or utcnow().isoformat()
                item["result"] = stored.get("result") or {}
        steps = strategy.get("steps") if isinstance(strategy.get("steps"), list) else []
        for step in steps:
            if isinstance(step, dict) and step.get("key") == "AGENT_DEPLOY_PREPARE":
                if any(isinstance(item, dict) and item.get("status") == "FAILED" for item in targets):
                    step["status"] = "FAILED"
                    step["message"] = "至少一个目标服务器部署失败"
                elif targets and all(isinstance(item, dict) and item.get("status") == "DEPLOYED" for item in targets):
                    step["status"] = "SUCCEEDED"
                    step["message"] = "所有目标服务器已完成镜像拉取、目录准备和运行时自检"
                else:
                    step["status"] = "RUNNING"
        strategy["targets"] = targets
        strategy["steps"] = steps
        strategy["updatedAt"] = utcnow().isoformat()
        deployment.strategy = strategy
