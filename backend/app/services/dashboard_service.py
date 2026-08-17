from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CrawlerProject, CrawlerServer, CrawlerTask, CrawlerTaskRun, SysUser
from app.services.permissions import is_super_admin, require_super_admin, scoped_company_id
from app.services.system_config_service import SystemConfigService


class DashboardService:
    def __init__(self, db: Session):
        self.db = db

    def summary(self, user: SysUser, detected_base_url: str = "", preflight_source: str = "AUTO") -> dict:
        require_super_admin(user)
        company_id = None if is_super_admin(user) else scoped_company_id(user)
        def count(model, *conditions):
            stmt = select(func.count()).select_from(model)
            for condition in conditions:
                stmt = stmt.where(condition)
            return self.db.scalar(stmt) or 0
        filters = [] if company_id is None else [CrawlerProject.company_id == company_id]
        server_filters = [] if company_id is None else [CrawlerServer.company_id == company_id]
        task_filters = [] if company_id is None else [CrawlerTask.company_id == company_id]
        run_filters = [] if company_id is None else [CrawlerTaskRun.company_id == company_id]
        project_count = count(CrawlerProject, *filters)
        server_count = count(CrawlerServer, *server_filters)
        task_count = count(CrawlerTask, *task_filters)
        running_count = count(CrawlerTaskRun, *run_filters, CrawlerTaskRun.run_status.in_(["ASSIGNED", "STARTING", "RUNNING"]))
        waiting_count = count(CrawlerTaskRun, *run_filters, CrawlerTaskRun.routing_status == "WAITING_RESOURCE")
        system_service = SystemConfigService(self.db)
        settings_payload = system_service.get_system_settings(detected_base_url, check_source=preflight_source, user=user, persist_snapshot=True)
        preflight = settings_payload.get("controlPlanePreflight") or {}
        runtime_evidence = preflight.get("runtimeEvidence") or {}
        online_agent_count = int(runtime_evidence.get("onlineAgentCount") or 0)
        runtime_issues: list[dict] = []
        if waiting_count > 0:
            if online_agent_count:
                message = f"当前有 {waiting_count} 个运行实例正在等待执行资源，已有 {online_agent_count} 个在线执行节点；平台会继续按容量和路由条件自动分配。"
            else:
                message = f"当前有 {waiting_count} 个运行实例正在等待执行资源，且没有在线执行节点提供实时心跳。"
            runtime_issues.append({
                "key": "waiting_resource_runtime",
                "label": "任务等待执行资源",
                "status": "WARN",
                "message": message,
                "blocking": False,
                "suggestion": "查看任务与执行节点当前状态；该提醒来自真实等待队列，不是预设配置清单。",
                "action": "查看任务与执行节点当前状态。",
                "verifyCommand": "",
                "impact": f"当前 {waiting_count} 个运行实例尚未获得执行资源。",
                "route": "/tasks",
                "actionLabel": "查看任务",
                "category": "任务运行",
                "canIgnore": False,
                "automationType": "MANUAL",
                "handler": "平台运行事实",
                "autoActionCommand": "",
                "actionEndpoint": "",
                "actionButtonLabel": "",
                "actionAvailable": False,
                "actionUnavailableReason": "",
                "executionChannel": "MANUAL",
                "manualCommand": "",
                "evidenceSource": "运行实例 routing_status=WAITING_RESOURCE",
                "evidenceScope": "当前等待资源的运行实例",
                "details": {"waitingCount": waiting_count, "onlineAgentCount": online_agent_count},
            })
        return {
            "projectCount": project_count,
            "serverCount": server_count,
            "taskCount": task_count,
            "runningCount": running_count,
            "waitingCount": waiting_count,
            "runtimeIssues": runtime_issues,
            "platformPreflight": preflight,
            "platformPreflightHistory": system_service.list_preflight_snapshots(8),
        }
