from __future__ import annotations

from typing import Any

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import CompanyResourceConfig, CrawlerAccountCredential, CrawlerAgent, CrawlerCompany, CrawlerProject, CrawlerProjectServer, CrawlerProjectTaskDefinition, CrawlerServer, CrawlerTask, CrawlerTaskSchedule, SysUser
from app.services.permissions import is_super_admin, require_company_scope
from app.services.system_config_service import SystemConfigService


class CompanySetupService:
    def __init__(self, db: Session):
        self.db = db

    def get_setup_status(self, user: SysUser, company_id: int) -> dict:
        require_company_scope(user, company_id)
        company = self.db.get(CrawlerCompany, company_id)
        if not company:
            raise AppError("公司不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        counts = self._counts(company_id)
        system_settings = SystemConfigService(self.db).get_system_settings()
        steps = self._steps(company_id, counts, system_settings, user)
        completed = sum(1 for item in steps if item["status"] == "DONE")
        mode = self._mode(counts, completed, len(steps))
        next_step = next((item for item in steps if item["status"] in {"MISSING", "ACTION", "RISK"} and not item.get("blocked")), steps[-1])
        return {
            "companyId": company.company_id,
            "companyName": company.company_name,
            "companyCode": company.company_code,
            "mode": mode,
            "summary": self._summary(mode),
            "completedCount": completed,
            "totalCount": len(steps),
            "nextStepKey": next_step["key"],
            "nextStepLabel": next_step["label"],
            "controlPlanePublicBaseUrl": system_settings.get("controlPlanePublicBaseUrl") or "",
            "controlPlanePublicBaseUrlSource": system_settings.get("controlPlanePublicBaseUrlSource") or "",
            "controlPlanePublicBaseUrlConfigured": bool(system_settings.get("controlPlanePublicBaseUrl")),
            "controlPlanePublicBaseUrlWarnings": system_settings.get("controlPlanePublicBaseUrlWarnings") or [],
            "steps": steps,
            "counts": counts,
        }

    def _counts(self, company_id: int) -> dict[str, Any]:
        resource_total = self.db.scalar(select(func.count()).select_from(CompanyResourceConfig).where(CompanyResourceConfig.company_id == company_id, CompanyResourceConfig.enabled.is_(True))) or 0
        resource_passed = self.db.scalar(
            select(func.count())
            .select_from(CompanyResourceConfig)
            .where(
                CompanyResourceConfig.company_id == company_id,
                CompanyResourceConfig.enabled.is_(True),
                CompanyResourceConfig.test_status.in_(["CONFIG_VALID", "CONNECTION_PASSED", "MANUAL_CONFIRMED"]),
            )
        ) or 0
        total_servers = self.db.scalar(select(func.count()).select_from(CrawlerServer).where(CrawlerServer.company_id == company_id, CrawlerServer.manage_status != "DISABLED")) or 0
        online_agents = self.db.scalar(select(func.count()).select_from(CrawlerAgent).join(CrawlerServer, CrawlerServer.server_id == CrawlerAgent.server_id).where(CrawlerServer.company_id == company_id, CrawlerAgent.connection_status == "ONLINE")) or 0
        projects = self.db.scalar(select(func.count()).select_from(CrawlerProject).where(CrawlerProject.company_id == company_id, CrawlerProject.status != "ARCHIVED")) or 0
        deployed_project_servers = self.db.scalar(select(func.count()).select_from(CrawlerProjectServer).where(CrawlerProjectServer.company_id == company_id, CrawlerProjectServer.deployment_status.in_(["DEPLOYED", "READY"]))) or 0
        task_definitions = self.db.scalar(select(func.count()).select_from(CrawlerProjectTaskDefinition).where(CrawlerProjectTaskDefinition.company_id == company_id, CrawlerProjectTaskDefinition.discovery_status == "ACTIVE", CrawlerProjectTaskDefinition.orchestration_status == "PENDING")) or 0
        platform_codes = list(self.db.scalars(select(CrawlerProjectTaskDefinition.platform_code).where(CrawlerProjectTaskDefinition.company_id == company_id, CrawlerProjectTaskDefinition.platform_code != "").distinct()).all())
        credential_platform_codes = list(self.db.scalars(select(CrawlerAccountCredential.platform_code).where(CrawlerAccountCredential.company_id == company_id).distinct()).all())
        account_total = self.db.scalar(select(func.count()).select_from(CrawlerAccountCredential).where(CrawlerAccountCredential.company_id == company_id, CrawlerAccountCredential.enabled.is_(True))) or 0
        account_need_attention = self.db.scalar(select(func.count()).select_from(CrawlerAccountCredential).where(CrawlerAccountCredential.company_id == company_id, CrawlerAccountCredential.enabled.is_(True), CrawlerAccountCredential.health_status.in_(["UNHEALTHY", "EXPIRED", "LOCKED"]))) or 0
        tasks = self.db.scalar(select(func.count()).select_from(CrawlerTask).where(CrawlerTask.company_id == company_id, CrawlerTask.status != "ARCHIVED")) or 0
        schedules = self.db.scalar(select(func.count()).select_from(CrawlerTaskSchedule).where(CrawlerTaskSchedule.company_id == company_id)) or 0
        return {
            "resourceTotal": int(resource_total),
            "resourcePassed": int(resource_passed),
            "serverTotal": int(total_servers),
            "onlineAgentCount": int(online_agents),
            "projectCount": int(projects),
            "deployedProjectServerCount": int(deployed_project_servers),
            "taskDefinitionCount": int(task_definitions),
            "platformCodeCount": len(set([*platform_codes, *credential_platform_codes])),
            "accountTotal": int(account_total),
            "accountNeedAttention": int(account_need_attention),
            "taskCount": int(tasks),
            "scheduleCount": int(schedules),
        }

    def _steps(self, company_id: int, c: dict[str, Any], system_settings: dict[str, Any], user: SysUser) -> list[dict[str, Any]]:
        platform_ready = bool(system_settings.get("controlPlanePublicBaseUrl"))
        database_done = c["resourcePassed"] > 0
        agent_done = c["onlineAgentCount"] > 0
        project_done = c["projectCount"] > 0 and c["taskDefinitionCount"] > 0
        deployed_done = c["deployedProjectServerCount"] > 0
        platform_done = c["platformCodeCount"] > 0
        account_done = c["accountTotal"] > 0 and c["accountNeedAttention"] == 0
        task_done = c["taskCount"] > 0
        platform_step_status = "DONE" if platform_ready else ("ACTION" if is_super_admin(user) else "BLOCKED")
        platform_blocked = not platform_ready and not is_super_admin(user)
        return [
            self._step("control_plane_url", "控制端公网回调地址", "代码构建流程和外部执行节点连接控制端服务时使用。", platform_step_status, "/settings", "去设置", {"configured": platform_ready}, blocked=platform_blocked, block_reason="请联系超级管理员配置控制端公网回调地址"),
            self._step("database", "公司数据库", "配置任务入库、缓存和原始数据存储。", "DONE" if database_done else "MISSING", "/resources", "去配置", {"resourceTotal": c["resourceTotal"], "resourcePassed": c["resourcePassed"]}),
            self._step("agent", "执行节点", "接入执行节点后才能部署项目和运行任务。", "DONE" if agent_done else "MISSING", "/servers", "去接入", {"onlineAgentCount": c["onlineAgentCount"], "serverTotal": c["serverTotal"]}),
            self._step("project", "爬虫项目", "部署项目只会准备版本和任务定义，不会自动启动任务。", "DONE" if project_done and deployed_done else ("BLOCKED" if not agent_done else "MISSING"), "/projects", "去部署", {"projectCount": c["projectCount"], "taskDefinitionCount": c["taskDefinitionCount"], "deployedProjectServerCount": c["deployedProjectServerCount"]}, blocked=not agent_done, block_reason="请先接入在线执行节点"),
            self._step("platform", "采集平台", "确认被采集的网站或系统，例如 Oilchem、JDL、CommerceHub。", "DONE" if platform_done else ("BLOCKED" if not project_done else "MISSING"), "/platforms", "去查看", {"platformCodeCount": c["platformCodeCount"]}, blocked=not project_done, block_reason="请先部署项目，然后发现任务"),
            self._step("account", "平台账号", "配置任务运行时使用的账号、Cookie 或 Token。", "DONE" if account_done else ("RISK" if c["accountNeedAttention"] else "MISSING"), "/accounts", "去添加", {"accountTotal": c["accountTotal"], "accountNeedAttention": c["accountNeedAttention"]}),
            self._step("task", "任务计划", "查看任务是否可执行，再手动执行或设置定时。", "DONE" if task_done else ("BLOCKED" if not (database_done and agent_done and project_done and account_done) else "MISSING"), "/tasks", "去查看", {"taskCount": c["taskCount"], "scheduleCount": c["scheduleCount"]}, blocked=not (database_done and agent_done and project_done and account_done), block_reason="请先完成数据库、执行节点、项目和账号配置"),
        ]

    @staticmethod
    def _step(key: str, label: str, description: str, status: str, route: str, action_label: str, metrics: dict[str, Any], blocked: bool = False, block_reason: str = "") -> dict[str, Any]:
        return {"key": key, "label": label, "description": description, "status": status, "route": route, "actionLabel": action_label, "metrics": metrics, "blocked": blocked, "blockReason": block_reason}

    @staticmethod
    def _mode(counts: dict[str, Any], completed: int, total: int) -> str:
        if completed == 0 or (counts["resourceTotal"] == 0 and counts["serverTotal"] == 0 and counts["projectCount"] == 0 and counts["accountTotal"] == 0):
            return "FIRST_SETUP"
        if completed >= total - 1 and counts["projectCount"] > 0 and counts["taskCount"] > 0:
            return "READY"
        if counts["projectCount"] > 0 or counts["taskCount"] > 0 or counts["serverTotal"] > 0:
            return "RECHECK"
        return "CONTINUE_SETUP"

    @staticmethod
    def _summary(mode: str) -> str:
        return {
            "FIRST_SETUP": "首次配置公司运行环境",
            "CONTINUE_SETUP": "继续完成公司配置",
            "RECHECK": "已有配置，检查待处理事项",
            "READY": "公司运行准备基本完成",
        }.get(mode, "检查公司运行准备情况")
