from __future__ import annotations

from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import SysUser
from app.repositories.task_schedule_panel import TaskSchedulePanelRepository
from app.schemas import TaskSchedulePanelQuery
from app.services.permissions import is_super_admin, require_project_role, scoped_company_id


class TaskSchedulePanelService:
    def __init__(self, db: Session):
        self.db = db
        self.panels = TaskSchedulePanelRepository(db)

    def list_panels(self, user: SysUser, query: TaskSchedulePanelQuery) -> dict:
        scoped_company = scoped_company_id(user, query.company_id)
        member_user_id = None if is_super_admin(user) else user.user_id

        if query.project_id is not None:
            project = require_project_role(self.db, user, query.project_id, "VIEWER")
            if scoped_company is not None and scoped_company != project.company_id:
                raise AppError("资源不存在", code=40401, http_status=404)
            scoped_company = project.company_id

        normalized = query.model_copy(update={
            "company_id": scoped_company,
            "task_name": self._clean(query.task_name),
            "task_code": self._clean(query.task_code),
            "entry_keyword": self._clean(query.entry_keyword),
            "task_group": self._clean(query.task_group),
            "task_platform": self._clean(query.task_platform),
            "task_status": self._upper(query.task_status),
            "schedule_status": self._upper(query.schedule_status),
            "last_run_status": self._upper(query.last_run_status),
        })
        rows, total = self.panels.list_panels(normalized, member_user_id=member_user_id)
        items = [self._panel_payload(row) for row in rows]
        return {"items": items, "total": total, "page": normalized.page, "page_size": normalized.page_size}

    @staticmethod
    def _clean(value: str | None) -> str | None:
        cleaned = (value or "").strip()
        return cleaned or None

    @staticmethod
    def _upper(value: str | None) -> str | None:
        cleaned = (value or "").strip().upper()
        return cleaned or None

    @staticmethod
    def _panel_payload(row: dict) -> dict:
        task_group = row.get("task_group") or ""
        project_name = row.get("project_name") or ""
        entry_module = row.get("entry_module") or ""
        entry_function = row.get("entry_function") or ""
        schedule_type = row.get("schedule_type") or "MANUAL"
        return {
            **row,
            "task_platform": task_group if task_group and task_group != "default" else project_name,
            "entry_path": f"{entry_module}:{entry_function}" if entry_function else entry_module,
            "server_name": row.get("server_name") or "",
            "server_code": row.get("server_code") or "",
            "server_ip": row.get("server_ip") or "",
            "owner_user_name": row.get("owner_user_name") or "",
            "schedule_status": row.get("schedule_status") or "NONE",
            "schedule_type": schedule_type,
            "cron_expression": row.get("cron_expression") or "",
            "schedule_timezone": row.get("schedule_timezone") or "",
            "overlap_policy": row.get("overlap_policy") or "QUEUE",
            "schedule_config": row.get("schedule_config") or {},
            "schedule_label": row.get("schedule_label") or ("手动执行" if schedule_type == "MANUAL" else ""),
            "last_run_status": row.get("last_run_status") or "NOT_RUN",
            "routing_status": row.get("routing_status") or "",
            "last_error_summary": row.get("last_error_summary") or "",
        }
