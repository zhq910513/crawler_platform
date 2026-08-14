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
        system_service = SystemConfigService(self.db)
        settings_payload = system_service.get_system_settings(detected_base_url, check_source=preflight_source, user=user, persist_snapshot=True)
        return {
            "projectCount": count(CrawlerProject, *filters),
            "serverCount": count(CrawlerServer, *server_filters),
            "taskCount": count(CrawlerTask, *task_filters),
            "runningCount": count(CrawlerTaskRun, *run_filters, CrawlerTaskRun.run_status.in_(["ASSIGNED", "STARTING", "RUNNING"])),
            "waitingCount": count(CrawlerTaskRun, *run_filters, CrawlerTaskRun.routing_status == "WAITING_RESOURCE"),
            "platformPreflight": settings_payload.get("controlPlanePreflight"),
            "platformPreflightHistory": system_service.list_preflight_snapshots(8),
        }
