from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError
from app.models import CrawlerAgent, CrawlerProject, CrawlerProjectServer, CrawlerRunEvent, CrawlerRunLog, CrawlerServer, CrawlerTask, CrawlerTaskRun
from app.schemas import AgentHeartbeat, AgentRunClaim, AgentRunHeartbeat, AgentRunResult
from app.services.routing_service import RoutingService
from app.services.state_machine import RUN_TERMINAL, safe_set_run_status, set_routing_status
from app.services.audit import write_operation_log
from app.utils import utcnow


class AgentService:
    def __init__(self, db: Session):
        self.db = db

    def heartbeat(self, agent: CrawlerAgent, payload: AgentHeartbeat) -> dict:
        server = self.db.get(CrawlerServer, agent.server_id)
        if not server:
            raise AppError("Agent 绑定服务器不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        replaced = bool(agent.agent_instance_id and agent.agent_instance_id != payload.agent_instance_id)
        if replaced:
            self._mark_agent_runs_lost(agent, "Agent 实例已被新进程替代")
        agent.agent_instance_id = payload.agent_instance_id
        agent.agent_version = payload.agent_version
        agent.protocol_version = payload.protocol_version
        agent.connection_status = "ONLINE"
        agent.last_heartbeat_at = utcnow()
        agent.capabilities = payload.capabilities
        agent.current_runs = payload.current_runs
        agent.last_error = payload.last_error
        self._update_server_health_capacity(server, payload)
        self._sync_project_server_scheduling(server)
        self.db.flush()
        RoutingService(self.db).reroute_or_wait_unclaimed(commit=False)
        self.db.commit()
        return {"serverId": server.server_id, "connectionStatus": agent.connection_status, "serverCapacityStatus": server.capacity_status, "replacedPreviousInstance": replaced}

    def claim_run(self, agent: CrawlerAgent, payload: AgentRunClaim) -> dict | None:
        if payload.agent_instance_id and payload.agent_instance_id != agent.agent_instance_id:
            raise AppError("Agent 实例已被替代，禁止领取任务", code=40373, http_status=status.HTTP_403_FORBIDDEN)
        server = self.db.get(CrawlerServer, agent.server_id)
        if not server or server.manage_status != "ENABLED" or server.health_status == "UNHEALTHY" or server.capacity_status in {"EXHAUSTED", "FULL", "DRAINED"} or agent.connection_status != "ONLINE":
            return None
        run = self.db.scalar(select(CrawlerTaskRun).where(CrawlerTaskRun.server_id == server.server_id, CrawlerTaskRun.run_status == "QUEUED", CrawlerTaskRun.routing_status == "ROUTED").order_by(CrawlerTaskRun.created_at.asc()))
        if not run:
            return None
        task = self.db.get(CrawlerTask, run.task_id)
        project = self.db.get(CrawlerProject, run.project_id)
        if not task or not project or task.status != "ENABLED" or project.status != "ENABLED" or project.online_status not in {"ONLINE", "READY"}:
            set_routing_status(run, "ROUTE_CANCELLED", reason="任务或项目状态已不可运行")
            self.db.commit()
            return None
        if not self._can_server_claim(project, run.server_id):
            run.server_id = None
            set_routing_status(run, "PENDING", reason="服务器项目调度状态已不可领取，等待重新路由")
            self.db.commit()
            return None
        ps = self.db.scalar(select(CrawlerProjectServer).where(CrawlerProjectServer.project_id == run.project_id, CrawlerProjectServer.server_id == server.server_id))
        if ps and ps.image_readiness_status in {"OUTDATED", "WARMING"}:
            ps.image_readiness_status = "READY"
            ps.disabled_reason = "Agent 领取任务时将按 digest 精确拉取并校验镜像"
        lease_token = secrets.token_hex(24)
        now = utcnow()
        claimed = self.db.execute(
            update(CrawlerTaskRun)
            .where(
                CrawlerTaskRun.run_id == run.run_id,
                CrawlerTaskRun.server_id == server.server_id,
                CrawlerTaskRun.run_status == "QUEUED",
                CrawlerTaskRun.routing_status == "ROUTED",
            )
            .values(
                run_status="ASSIGNED",
                agent_id=agent.agent_id,
                lease_token=lease_token,
                lease_expires_at=now + timedelta(seconds=settings.agent_lease_seconds),
                heartbeat_at=now,
                updated_at=now,
            )
        ).rowcount
        if claimed != 1:
            self.db.rollback()
            return None
        self.db.refresh(run)
        self.db.add(CrawlerRunEvent(company_id=run.company_id, run_id=run.run_id, event_type="AGENT_CLAIMED", event_level="INFO", stage="ROUTE", message="Agent 已领取运行实例", payload_json={"agentId": agent.agent_id, "serverId": server.server_id}))
        self.db.commit()
        return {
            "runId": run.run_id,
            "leaseToken": lease_token,
            "companyId": run.company_id,
            "projectId": run.project_id,
            "projectCode": project.project_code,
            "taskId": task.task_id,
            "taskCode": task.task_code,
            "imageRepository": run.image_repository,
            "imageDigest": run.image_digest,
            "entryModule": run.entry_module,
            "entryFunction": run.entry_function,
            "parameters": run.parameters_snapshot,
            "cpuLimit": run.cpu_limit,
            "memoryLimitMb": run.memory_limit_mb,
            "timeoutSeconds": run.timeout_seconds,
            "runtimeMode": run.runtime_mode,
            "taskGroup": run.task_group,
            "ioClass": run.io_class,
            "shmSizeMb": run.shm_size_mb,
            "logLimitMb": run.log_limit_mb,
            "resourceLocks": run.resource_locks or [],
            "exclusiveMode": run.exclusive_mode,
            "shardIndex": run.shard_index,
            "shardCount": run.shard_count,
        }

    def run_heartbeat(self, agent: CrawlerAgent, payload: AgentRunHeartbeat) -> dict:
        if payload.agent_instance_id and payload.agent_instance_id != agent.agent_instance_id:
            raise AppError("Agent 实例已被替代", code=40373, http_status=status.HTTP_403_FORBIDDEN)
        run = self.db.get(CrawlerTaskRun, payload.run_id)
        if not run or run.agent_id != agent.agent_id or run.lease_token != payload.lease_token:
            raise AppError("运行租约无效", code=40370, http_status=status.HTTP_403_FORBIDDEN)
        if run.run_status == "CANCEL_REQUESTED":
            self.db.commit()
            return {"cancelRequested": True}
        if run.run_status == "ASSIGNED":
            safe_set_run_status(run, "STARTING")
            self.db.add(CrawlerRunEvent(company_id=run.company_id, run_id=run.run_id, event_type="CONTAINER_STARTING", event_level="INFO", stage="DOCKER", message=payload.message or "任务容器准备启动", payload_json={}))
        elif run.run_status == "STARTING":
            safe_set_run_status(run, "RUNNING")
            run.started_at = run.started_at or utcnow()
            self.db.add(CrawlerRunEvent(company_id=run.company_id, run_id=run.run_id, event_type="SPIDER_STARTED", event_level="INFO", stage="BOOT", message=payload.message or "爬虫任务已开始运行", payload_json={}))
        elif run.run_status in RUN_TERMINAL:
            raise AppError("运行实例已结束", code=40374, http_status=status.HTTP_403_FORBIDDEN)
        run.heartbeat_at = utcnow()
        run.lease_expires_at = utcnow() + timedelta(seconds=settings.agent_lease_seconds)
        if payload.message:
            self.db.add(CrawlerRunLog(company_id=run.company_id, run_id=run.run_id, log_level="INFO", message=payload.message))
        self.db.commit()
        return {"cancelRequested": False}

    def finish_run(self, agent: CrawlerAgent, payload: AgentRunResult) -> CrawlerTaskRun:
        if payload.agent_instance_id and payload.agent_instance_id != agent.agent_instance_id:
            raise AppError("Agent 实例已被替代", code=40373, http_status=status.HTTP_403_FORBIDDEN)
        run = self.db.get(CrawlerTaskRun, payload.run_id)
        if not run or run.agent_id != agent.agent_id or run.lease_token != payload.lease_token:
            raise AppError("运行租约无效", code=40370, http_status=status.HTTP_403_FORBIDDEN)
        if run.run_status not in RUN_TERMINAL:
            target = "CANCELLED" if run.run_status == "CANCEL_REQUESTED" and payload.run_status == "CANCELLED" else payload.run_status
            safe_set_run_status(run, target, message=payload.error_message)
        run.finished_at = utcnow()
        run.result_payload = payload.result_payload
        run.error_message = payload.error_message
        run.lease_expires_at = None
        if payload.error_message:
            self.db.add(CrawlerRunLog(company_id=run.company_id, run_id=run.run_id, log_level="ERROR", message=payload.error_message))
        self.db.add(CrawlerRunEvent(company_id=run.company_id, run_id=run.run_id, event_type=f"RUN_{run.run_status}", event_level="INFO" if run.run_status in {"SUCCEEDED", "PARTIAL_SUCCESS"} else "ERROR", stage="FINISH", message=payload.error_message or "运行实例已结束", payload_json={"runStatus": run.run_status}))
        if run.run_status not in {"SUCCEEDED", "PARTIAL_SUCCESS", "CANCELLED"}:
            run.failed_stage = run.failed_stage or "FINISH"
            run.error_type = run.error_type or self._infer_error_type(payload.error_message)
            run.error_summary = run.error_summary or (payload.error_message[:1000] if payload.error_message else "任务执行失败")
            run.retryable = run.retryable if run.retryable is not None else run.run_status in {"TIMED_OUT", "LOST"}
            run.diagnosis_json = run.diagnosis_json or {"summary": run.error_summary, "suggestion": "请查看生命周期时间线和错误附近日志。"}
        from app.services.run_service import RunService
        run_service = RunService(self.db)
        run_service.maybe_retry(run)
        run_service.aggregate_sharded_parent(run.parent_run_id)
        self.db.commit()
        return run

    def _can_server_claim(self, project: CrawlerProject, server_id: int | None) -> bool:
        if not server_id:
            return False
        ps = self.db.scalar(select(CrawlerProjectServer).where(CrawlerProjectServer.project_id == project.project_id, CrawlerProjectServer.server_id == server_id))
        if not ps:
            return bool(project.allow_company_pool_fallback)
        return ps.deployment_status == "DEPLOYED" and ps.scheduling_status in {"ENABLED", "RECOVERING"} and ps.image_readiness_status in {"READY", "OUTDATED", "WARMING"}

    def _update_server_health_capacity(self, server: CrawlerServer, payload: AgentHeartbeat) -> None:
        metrics = dict(server.metrics or {})
        metrics.update({
            "dockerStatus": payload.docker_status,
            "cpuUsage": payload.cpu_usage,
            "memoryUsage": payload.memory_usage,
            "diskUsage": payload.disk_usage,
            "inodeUsage": payload.inode_usage,
            "loadAverage": payload.load_average,
            "runningContainers": payload.running_containers,
            "availableSlots": payload.available_slots,
            "maxSlots": payload.max_slots if payload.max_slots is not None else server.max_container_slots,
            "currentRuns": payload.current_runs.get("runIds", []) if isinstance(payload.current_runs, dict) else [],
            "projectDataRootWritable": payload.project_data_root_writable,
            "dockerSockAccessible": payload.docker_sock_accessible,
            "timezone": payload.timezone,
            "lastError": payload.last_error,
            "lastHeartbeatAt": utcnow().isoformat(),
        })
        raw_unhealthy = payload.health_status == "UNHEALTHY" or payload.docker_status.upper() != "OK" or payload.docker_sock_accessible is False
        raw_exhausted = payload.capacity_status in {"FULL", "DRAINED", "EXHAUSTED"} or payload.available_slots <= 0
        raw_pressure = payload.capacity_status == "BUSY" or 0 < payload.available_slots <= max(1, server.max_container_slots // 4)
        bad = int(metrics.get("badHealthCount") or 0)
        good = int(metrics.get("goodHealthCount") or 0)
        if raw_unhealthy:
            bad += 1; good = 0
        else:
            good += 1; bad = 0
        metrics["badHealthCount"] = bad
        metrics["goodHealthCount"] = good
        if server.health_status == "UNKNOWN" and not raw_unhealthy:
            server.health_status = "HEALTHY"
        elif bad >= 3:
            server.health_status = "UNHEALTHY"
        elif good >= 3 and server.health_status == "UNHEALTHY":
            server.health_status = "DEGRADED"
        elif good >= 5:
            server.health_status = "HEALTHY"
        cap_bad = int(metrics.get("badCapacityCount") or 0)
        cap_good = int(metrics.get("goodCapacityCount") or 0)
        if raw_exhausted:
            cap_bad += 1; cap_good = 0
        else:
            cap_good += 1; cap_bad = 0
        metrics["badCapacityCount"] = cap_bad
        metrics["goodCapacityCount"] = cap_good
        if server.capacity_status == "UNKNOWN" and not raw_exhausted:
            server.capacity_status = "PRESSURE" if raw_pressure else "NORMAL"
        elif cap_bad >= 3:
            server.capacity_status = "EXHAUSTED"
        elif raw_pressure:
            server.capacity_status = "PRESSURE"
        elif cap_good >= 5 or server.capacity_status == "UNKNOWN":
            server.capacity_status = "NORMAL"
        server.metrics = metrics

    def _sync_project_server_scheduling(self, server: CrawlerServer) -> None:
        items = list(self.db.scalars(select(CrawlerProjectServer).where(CrawlerProjectServer.server_id == server.server_id, CrawlerProjectServer.deployment_status == "DEPLOYED")).all())
        unhealthy = server.health_status == "UNHEALTHY" or server.capacity_status in {"EXHAUSTED", "FULL", "DRAINED"} or server.manage_status != "ENABLED"
        recovered = server.health_status in {"HEALTHY", "DEGRADED"} and server.capacity_status in {"NORMAL", "PRESSURE", "BUSY"} and server.manage_status == "ENABLED"
        for ps in items:
            if unhealthy and ps.auto_eject_enabled and ps.scheduling_status in {"ENABLED", "RECOVERING"}:
                before = {"projectServerId": ps.project_server_id, "schedulingStatus": ps.scheduling_status, "disabledReason": ps.disabled_reason}
                ps.scheduling_status = "AUTO_EJECTED"
                ps.disabled_reason = "Agent 连续检测到服务器异常或资源不足，系统自动摘除"
                write_operation_log(self.db, None, None, operation_type="AUTO_EJECT_PROJECT_SERVER", resource_type="project_server", resource_id=str(ps.project_server_id), before_data=before, after_data={"projectServerId": ps.project_server_id, "schedulingStatus": ps.scheduling_status, "disabledReason": ps.disabled_reason})
            elif recovered and ps.auto_recover_enabled and ps.scheduling_status == "AUTO_EJECTED":
                before = {"projectServerId": ps.project_server_id, "schedulingStatus": ps.scheduling_status, "disabledReason": ps.disabled_reason}
                ps.scheduling_status = "RECOVERING"
                ps.disabled_reason = "服务器已恢复，进入恢复观察"
                write_operation_log(self.db, None, None, operation_type="RECOVER_PROJECT_SERVER", resource_type="project_server", resource_id=str(ps.project_server_id), before_data=before, after_data={"projectServerId": ps.project_server_id, "schedulingStatus": ps.scheduling_status, "disabledReason": ps.disabled_reason})
            elif recovered and ps.auto_recover_enabled and ps.scheduling_status == "RECOVERING":
                before = {"projectServerId": ps.project_server_id, "schedulingStatus": ps.scheduling_status, "disabledReason": ps.disabled_reason}
                ps.scheduling_status = "ENABLED"
                ps.disabled_reason = ""
                write_operation_log(self.db, None, None, operation_type="ENABLE_RECOVERED_PROJECT_SERVER", resource_type="project_server", resource_id=str(ps.project_server_id), before_data=before, after_data={"projectServerId": ps.project_server_id, "schedulingStatus": ps.scheduling_status, "disabledReason": ps.disabled_reason})

    @staticmethod
    def _infer_error_type(message: str) -> str:
        text = (message or "").lower()
        if "timeout" in text or "超时" in text:
            return "NETWORK_TIMEOUT"
        if "docker" in text or "container" in text or "容器" in text:
            return "DOCKER_ERROR"
        if "permission" in text or "权限" in text:
            return "PERMISSION_ERROR"
        return "UNKNOWN_ERROR"

    def _mark_agent_runs_lost(self, agent: CrawlerAgent, message: str) -> None:
        runs = list(self.db.scalars(select(CrawlerTaskRun).where(CrawlerTaskRun.agent_id == agent.agent_id, CrawlerTaskRun.run_status.in_(["ASSIGNED", "STARTING", "RUNNING", "CANCEL_REQUESTED"]))).all())
        for run in runs:
            safe_set_run_status(run, "LOST", message=message)
            run.finished_at = utcnow()
            run.lease_expires_at = None
