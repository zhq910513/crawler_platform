from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.utils import utcnow
from app.models import CrawlerCompany, CrawlerProject, CrawlerRunContainerSnapshot, CrawlerServer, CrawlerTask, CrawlerTaskRun, SysUser
from app.services.permissions import scoped_company_id

ACTIVE_RUN_STATUSES = {"QUEUED", "ASSIGNED", "STARTING", "RUNNING", "CANCEL_REQUESTED"}
FAILED_RUN_STATUSES = {"FAILED", "TIMED_OUT", "LOST", "CANCELLED"}
CONTAINER_BAD = {"FAILED", "TIMED_OUT", "OOM_KILLED", "LOST"}
SERVER_BAD = {"UNHEALTHY", "OFFLINE"}
SERVER_WARN = {"BUSY", "FULL", "EXHAUSTED", "DRAINED"}


class RunningCenterService:
    """Company -> project -> task runtime cockpit for normal company users.

    This service intentionally hides releaseId/imageDigest/container details from the
    main list and returns them only in task detail blocks. It follows 1.0.27's
    product model: employees first care about company projects, then project tasks,
    then the concrete run/container/server evidence when something is abnormal.
    """

    def __init__(self, db: Session):
        self.db = db

    def summary(self, user: SysUser, company_id: int | None = None) -> dict[str, Any]:
        scoped = scoped_company_id(user, company_id)
        company = self._resolve_company(scoped)
        project_rows = self._projects(scoped)
        project_ids = [p.project_id for p in project_rows]
        task_rows = self._tasks(project_ids)
        task_ids = [t.task_id for t in task_rows]
        latest_runs = self._latest_runs(task_ids)
        latest_containers = self._latest_containers([r.run_id for r in latest_runs.values()])
        servers = self._servers(scoped)
        server_by_id = {s.server_id: s for s in servers}
        tasks_by_project: dict[int, list[CrawlerTask]] = defaultdict(list)
        for task in task_rows:
            tasks_by_project[task.project_id].append(task)

        projects = []
        for project in project_rows:
            tasks = tasks_by_project.get(project.project_id, [])
            task_items = [self._task_item(task, latest_runs.get(task.task_id), latest_containers, server_by_id) for task in tasks]
            project_state = self._project_state(project, task_items)
            projects.append({
                "projectId": project.project_id,
                "projectName": project.project_name,
                "projectCode": project.project_code,
                "projectStatus": project_state["status"],
                "projectStatusText": project_state["text"],
                "projectAdvice": project_state["advice"],
                "projectAction": project_state["action"],
                "singleTaskProject": len(task_items) == 1,
                "taskCount": len(task_items),
                "runningTaskCount": sum(1 for item in task_items if item["taskState"] == "RUNNING"),
                "failedTaskCount": sum(1 for item in task_items if item["taskState"] in {"FAILED", "CONTAINER_ERROR", "SERVER_ERROR", "ACCOUNT_ERROR", "DB_ERROR"}),
                "readyTaskCount": sum(1 for item in task_items if item["taskState"] in {"READY", "SUCCESS"}),
                "recentResultText": self._recent_result_text(task_items),
                "latestVersion": getattr(project, "latest_version", "") or "",
                "deploymentText": "已部署" if task_items else "待部署或待创建任务",
                "tasks": task_items,
            })

        overview = self._overview(projects, servers)
        return {
            "company": {
                "companyId": company.company_id if company else scoped,
                "companyName": company.company_name if company else "当前公司",
            },
            "overview": overview,
            "layers": ["公司", "项目", "任务", "执行详情"],
            "projects": projects,
            "updatedAt": utcnow().isoformat(),
        }

    def _resolve_company(self, company_id: int | None) -> CrawlerCompany | None:
        if company_id is None:
            return None
        return self.db.get(CrawlerCompany, company_id)

    def _projects(self, company_id: int | None) -> list[CrawlerProject]:
        stmt = select(CrawlerProject).order_by(CrawlerProject.updated_at.desc(), CrawlerProject.created_at.desc())
        if company_id is not None:
            stmt = stmt.where(CrawlerProject.company_id == company_id)
        return list(self.db.scalars(stmt).all())

    def _tasks(self, project_ids: list[int]) -> list[CrawlerTask]:
        if not project_ids:
            return []
        return list(self.db.scalars(select(CrawlerTask).where(CrawlerTask.project_id.in_(project_ids), CrawlerTask.status != "ARCHIVED").order_by(CrawlerTask.project_id.asc(), CrawlerTask.created_at.asc())).all())

    def _latest_runs(self, task_ids: list[int]) -> dict[int, CrawlerTaskRun]:
        if not task_ids:
            return {}
        rows = list(self.db.scalars(select(CrawlerTaskRun).where(CrawlerTaskRun.task_id.in_(task_ids)).order_by(CrawlerTaskRun.task_id.asc(), desc(CrawlerTaskRun.created_at))).all())
        result: dict[int, CrawlerTaskRun] = {}
        for row in rows:
            result.setdefault(row.task_id, row)
        return result

    def _latest_containers(self, run_ids: list[int]) -> dict[int, CrawlerRunContainerSnapshot]:
        if not run_ids:
            return {}
        rows = list(self.db.scalars(select(CrawlerRunContainerSnapshot).where(CrawlerRunContainerSnapshot.run_id.in_(run_ids)).order_by(CrawlerRunContainerSnapshot.run_id.asc(), desc(CrawlerRunContainerSnapshot.observed_at))).all())
        result: dict[int, CrawlerRunContainerSnapshot] = {}
        for row in rows:
            result.setdefault(row.run_id, row)
        return result

    def _servers(self, company_id: int | None) -> list[CrawlerServer]:
        stmt = select(CrawlerServer)
        if company_id is not None:
            stmt = stmt.where(CrawlerServer.company_id == company_id)
        return list(self.db.scalars(stmt).all())

    def _task_item(self, task: CrawlerTask, run: CrawlerTaskRun | None, containers: dict[int, CrawlerRunContainerSnapshot], servers: dict[int, CrawlerServer]) -> dict[str, Any]:
        container = containers.get(run.run_id) if run else None
        server = servers.get(run.server_id) if run and run.server_id else None
        state = self._task_state(task, run, container, server)
        return {
            "taskId": task.task_id,
            "taskName": task.task_name,
            "taskCode": task.task_code,
            "taskState": state["status"],
            "taskStateText": state["text"],
            "stateLevel": state["level"],
            "advice": state["advice"],
            "primaryAction": state["action"],
            "scheduleText": self._schedule_text(task),
            "latestRun": self._run_payload(run),
            "container": self._container_payload(container),
            "server": self._server_payload(server),
            "debug": {
                "runtimeMode": task.runtime_mode,
                "executionMode": task.execution_mode,
                "taskGroup": task.task_group,
            },
        }

    def _task_state(self, task: CrawlerTask, run: CrawlerTaskRun | None, container: CrawlerRunContainerSnapshot | None, server: CrawlerServer | None) -> dict[str, str]:
        if task.status != "ENABLED":
            return self._state("NEED_CONFIG", "需要配置", "任务尚未启用，建议先确认数据库、账号和调度配置。", "去任务调度", "warning")
        if server and server.health_status in SERVER_BAD:
            return self._state("SERVER_ERROR", "节点异常", "执行节点离线或异常，建议查看执行节点状态。", "查看执行节点", "danger")
        if container and container.container_status in CONTAINER_BAD:
            if container.container_status == "OOM_KILLED":
                return self._state("CONTAINER_ERROR", "容器内存不足", "本次执行容器被内存限制终止，建议降低并发或提高内存。", "查看容器", "danger")
            return self._state("CONTAINER_ERROR", "容器异常", "本次执行容器异常，建议先查看日志和容器详情。", "查看容器", "danger")
        if not run:
            return self._state("READY", "可执行", "任务已创建，建议先手动执行一次验证结果。", "手动执行", "success")
        if run.run_status in ACTIVE_RUN_STATUSES:
            return self._state("RUNNING", "运行中", "任务正在执行，可查看实时日志、容器和节点状态。", "查看详情", "primary")
        if run.run_status == "SUCCEEDED":
            return self._state("SUCCESS", "最近成功", "最近一次执行成功，可查看历史记录或配置定时。", "查看历史", "success")
        if run.run_status in FAILED_RUN_STATUSES:
            if "ACCOUNT" in (run.error_type or "") or "COOKIE" in (run.error_summary or "") or "TOKEN" in (run.error_summary or ""):
                return self._state("ACCOUNT_ERROR", "账号异常", "任务失败可能与账号或登录状态有关，建议更新平台账号。", "更新账号", "danger")
            if "DB" in (run.error_type or "") or "数据库" in (run.error_summary or run.error_message or ""):
                return self._state("DB_ERROR", "数据库异常", "任务失败可能与数据库连接或入库有关，建议校验数据资源配置。", "校验数据资源", "danger")
            return self._state("FAILED", "执行失败", "任务执行失败，建议先查看日志，再决定是否重新执行。", "查看日志", "danger")
        return self._state("UNKNOWN", "待确认", "当前状态需要进一步查看执行详情。", "查看详情", "info")

    @staticmethod
    def _state(status: str, text: str, advice: str, action: str, level: str) -> dict[str, str]:
        return {"status": status, "text": text, "advice": advice, "action": action, "level": level}

    def _project_state(self, project: CrawlerProject, tasks: list[dict[str, Any]]) -> dict[str, str]:
        if not tasks:
            return {"status": "NEED_TASK", "text": "待创建任务", "advice": "项目已存在，但尚未创建可运行任务。", "action": "去任务调度"}
        states = {item["taskState"] for item in tasks}
        if states & {"SERVER_ERROR", "CONTAINER_ERROR", "FAILED", "ACCOUNT_ERROR", "DB_ERROR"}:
            return {"status": "HAS_ISSUE", "text": "有异常", "advice": "项目内存在需要处理的任务，建议展开查看。", "action": "查看任务"}
        if "RUNNING" in states:
            return {"status": "RUNNING", "text": "运行中", "advice": "项目内有任务正在运行。", "action": "查看任务"}
        if states <= {"SUCCESS", "READY"}:
            return {"status": "NORMAL", "text": "正常", "advice": "项目任务已就绪，可手动执行或查看调度。", "action": "查看任务"}
        return {"status": "NEED_CONFIG", "text": "待完善", "advice": "项目还有配置未完成。", "action": "继续配置"}

    @staticmethod
    def _recent_result_text(tasks: list[dict[str, Any]]) -> str:
        if not tasks:
            return "暂无任务"
        for item in tasks:
            if item["taskState"] in {"FAILED", "CONTAINER_ERROR", "SERVER_ERROR", "ACCOUNT_ERROR", "DB_ERROR"}:
                return f"{item['taskName']}：{item['taskStateText']}"
        for item in tasks:
            if item["taskState"] == "RUNNING":
                return f"{item['taskName']}：运行中"
        return "任务状态正常"

    @staticmethod
    def _overview(projects: list[dict[str, Any]], servers: list[CrawlerServer]) -> dict[str, int]:
        tasks = [task for project in projects for task in project["tasks"]]
        return {
            "projectCount": len(projects),
            "taskCount": len(tasks),
            "runningCount": sum(1 for task in tasks if task["taskState"] == "RUNNING"),
            "failedCount": sum(1 for task in tasks if task["taskState"] in {"FAILED", "CONTAINER_ERROR", "SERVER_ERROR", "ACCOUNT_ERROR", "DB_ERROR"}),
            "readyCount": sum(1 for task in tasks if task["taskState"] in {"READY", "SUCCESS"}),
            "onlineServerCount": sum(1 for server in servers if server.health_status == "HEALTHY"),
            "issueServerCount": sum(1 for server in servers if server.health_status in SERVER_BAD or server.capacity_status in SERVER_WARN),
        }

    @staticmethod
    def _schedule_text(task: CrawlerTask) -> str:
        # The running center intentionally avoids exposing cron fields here. The
        # detailed schedule is still managed in Task Scheduling.
        return "查看任务调度"

    @staticmethod
    def _run_payload(run: CrawlerTaskRun | None) -> dict[str, Any] | None:
        if not run:
            return None
        return {
            "runId": run.run_id,
            "runStatus": run.run_status,
            "routingStatus": run.routing_status,
            "routingReason": run.routing_reason,
            "releaseId": run.release_id,
            "imageDigest": run.image_digest,
            "startedAt": run.started_at,
            "finishedAt": run.finished_at,
            "createdAt": run.created_at,
            "errorSummary": run.error_summary or run.error_message,
            "failedStage": run.failed_stage,
            "errorType": run.error_type,
            "retryable": run.retryable,
        }

    @staticmethod
    def _container_payload(container: CrawlerRunContainerSnapshot | None) -> dict[str, Any] | None:
        if not container:
            return None
        return {
            "snapshotId": container.snapshot_id,
            "containerId": container.container_id,
            "containerName": container.container_name,
            "imageDigest": container.image_digest,
            "containerStatus": container.container_status,
            "exitCode": container.exit_code,
            "oomKilled": container.oom_killed,
            "restartCount": container.restart_count,
            "cpuUsage": container.cpu_usage,
            "memoryUsageMb": container.memory_usage_mb,
            "startedAt": container.started_at,
            "finishedAt": container.finished_at,
            "lastLogLine": container.last_log_line,
            "observedAt": container.observed_at,
        }

    @staticmethod
    def _server_payload(server: CrawlerServer | None) -> dict[str, Any] | None:
        if not server:
            return None
        metrics = server.metrics or {}
        return {
            "serverId": server.server_id,
            "serverName": server.server_name,
            "serverCode": server.server_code,
            "serverIp": server.server_ip,
            "healthStatus": server.health_status,
            "capacityStatus": server.capacity_status,
            "dockerStatus": metrics.get("dockerStatus") or metrics.get("docker_status") or "UNKNOWN",
            "cpuUsage": metrics.get("cpuUsage") or metrics.get("cpu_usage"),
            "memoryUsage": metrics.get("memoryUsage") or metrics.get("memory_usage"),
            "diskUsage": metrics.get("diskUsage") or metrics.get("disk_usage"),
            "availableSlots": metrics.get("availableSlots") or metrics.get("available_slots"),
            "maxSlots": metrics.get("maxSlots") or metrics.get("max_slots") or server.max_container_slots,
            "lastHeartbeatAt": metrics.get("lastHeartbeatAt") or metrics.get("last_heartbeat_at"),
            "lastError": metrics.get("lastError") or metrics.get("last_error") or "",
        }
