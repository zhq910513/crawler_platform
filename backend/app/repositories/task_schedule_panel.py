from __future__ import annotations

from typing import Any

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models import (
    CrawlerCompany,
    CrawlerProject,
    CrawlerProjectMember,
    CrawlerProjectServer,
    CrawlerProjectTaskDefinition,
    CrawlerServer,
    CrawlerTask,
    CrawlerTaskRun,
    CrawlerTaskSchedule,
    CrawlerTaskServerTarget,
    SysUser,
)
from app.schemas import TaskSchedulePanelQuery


class TaskSchedulePanelRepository:
    def __init__(self, db: Session):
        self.db = db


    def list_pending_definitions(self, query: TaskSchedulePanelQuery, *, member_user_id: int | None = None) -> tuple[list[dict[str, Any]], int]:
        if query.task_status:
            return [], 0
        filters = [CrawlerProjectTaskDefinition.definition_status == "AVAILABLE"]
        if query.company_id is not None:
            filters.append(CrawlerProjectTaskDefinition.company_id == query.company_id)
        if query.project_id is not None:
            filters.append(CrawlerProjectTaskDefinition.project_id == query.project_id)
        if query.task_name:
            filters.append(CrawlerProjectTaskDefinition.task_name.like(f"%{query.task_name}%"))
        if query.task_code:
            filters.append(CrawlerProjectTaskDefinition.definition_key.like(f"%{query.task_code}%"))
        if query.entry_keyword:
            filters.append(or_(CrawlerProjectTaskDefinition.entry_module.like(f"%{query.entry_keyword}%"), CrawlerProjectTaskDefinition.entry_function.like(f"%{query.entry_keyword}%")))
        if query.task_group:
            filters.append(CrawlerProjectTaskDefinition.task_group.like(f"%{query.task_group}%"))
        if query.task_platform:
            filters.append(or_(CrawlerProjectTaskDefinition.platform_code.like(f"%{query.task_platform}%"), CrawlerProject.project_name.like(f"%{query.task_platform}%"), CrawlerProjectTaskDefinition.task_group.like(f"%{query.task_platform}%")))
        if query.schedule_status and query.schedule_status != "NONE":
            return [], 0
        if query.last_run_status and query.last_run_status != "NOT_RUN":
            return [], 0
        if query.owner_user_id is not None:
            return [], 0
        if query.server_id is not None:
            filters.append(
                exists(
                    select(1).where(
                        CrawlerProjectServer.project_id == CrawlerProjectTaskDefinition.project_id,
                        CrawlerProjectServer.server_id == query.server_id,
                        CrawlerProjectServer.deployment_status == "DEPLOYED",
                        CrawlerProjectServer.scheduling_status.notin_(["DISABLED", "DRAINING"]),
                    )
                )
            )
        if member_user_id is not None:
            filters.append(
                exists(
                    select(1).where(
                        CrawlerProjectMember.project_id == CrawlerProjectTaskDefinition.project_id,
                        CrawlerProjectMember.user_id == member_user_id,
                    )
                )
            )

        from_clause = (
            CrawlerProjectTaskDefinition.__table__
            .join(CrawlerProject.__table__, CrawlerProject.project_id == CrawlerProjectTaskDefinition.project_id)
            .join(CrawlerCompany.__table__, CrawlerCompany.company_id == CrawlerProjectTaskDefinition.company_id)
        )
        columns = [
            CrawlerProjectTaskDefinition.definition_id.label("definition_id"),
            CrawlerProjectTaskDefinition.company_id.label("company_id"),
            CrawlerCompany.company_name.label("company_name"),
            CrawlerProjectTaskDefinition.project_id.label("project_id"),
            CrawlerProject.project_name.label("project_name"),
            CrawlerProjectTaskDefinition.definition_key.label("definition_key"),
            CrawlerProjectTaskDefinition.task_name.label("task_name"),
            CrawlerProjectTaskDefinition.entry_module.label("entry_module"),
            CrawlerProjectTaskDefinition.entry_function.label("entry_function"),
            CrawlerProjectTaskDefinition.platform_code.label("platform_code"),
            CrawlerProjectTaskDefinition.task_group.label("task_group"),
            CrawlerProjectTaskDefinition.suggested_cron.label("suggested_cron"),
            CrawlerProjectTaskDefinition.required_configs.label("required_configs"),
            CrawlerProjectTaskDefinition.required_credentials.label("required_credentials"),
            CrawlerProjectTaskDefinition.contract_status.label("contract_status"),
            CrawlerProjectTaskDefinition.contract_warnings.label("contract_warnings"),
            CrawlerProjectTaskDefinition.definition_status.label("definition_status"),
            CrawlerProjectTaskDefinition.updated_at.label("updated_at"),
        ]
        total = int(self.db.scalar(select(func.count()).select_from(CrawlerProjectTaskDefinition.__table__.join(CrawlerProject.__table__, CrawlerProject.project_id == CrawlerProjectTaskDefinition.project_id).join(CrawlerCompany.__table__, CrawlerCompany.company_id == CrawlerProjectTaskDefinition.company_id)).where(*filters)) or 0)
        stmt = (
            select(*columns)
            .select_from(from_clause)
            .where(*filters)
            .order_by(CrawlerProjectTaskDefinition.updated_at.desc(), CrawlerProjectTaskDefinition.definition_id.desc())
            .limit(200)
        )
        return [dict(row) for row in self.db.execute(stmt).mappings().all()], total

    def list_panels(self, query: TaskSchedulePanelQuery, *, member_user_id: int | None = None) -> tuple[list[dict[str, Any]], int]:
        latest_run_ids = (
            select(CrawlerTaskRun.task_id, func.max(CrawlerTaskRun.run_id).label("last_run_id"))
            .where(CrawlerTaskRun.parent_run_id.is_(None))
            .group_by(CrawlerTaskRun.task_id)
            .subquery("latest_run_ids")
        )
        last_run = aliased(CrawlerTaskRun, name="last_run")

        primary_target_server_id = (
            select(CrawlerTaskServerTarget.server_id)
            .where(
                CrawlerTaskServerTarget.task_id == CrawlerTask.task_id,
                CrawlerTaskServerTarget.enabled.is_(True),
            )
            .order_by(CrawlerTaskServerTarget.priority.asc(), CrawlerTaskServerTarget.target_id.asc())
            .limit(1)
            .correlate(CrawlerTask)
            .scalar_subquery()
        )
        primary_project_server_id = (
            select(CrawlerProjectServer.server_id)
            .where(
                CrawlerProjectServer.project_id == CrawlerTask.project_id,
                CrawlerProjectServer.deployment_status == "DEPLOYED",
                CrawlerProjectServer.scheduling_status.notin_(["DISABLED", "DRAINING"]),
            )
            .order_by(CrawlerProjectServer.priority.asc(), CrawlerProjectServer.project_server_id.asc())
            .limit(1)
            .correlate(CrawlerTask)
            .scalar_subquery()
        )
        display_server_id = func.coalesce(primary_target_server_id, last_run.server_id, primary_project_server_id)
        owner_name = func.coalesce(func.nullif(SysUser.nick_name, ""), SysUser.user_name)
        error_summary = case(
            (and_(last_run.error_summary.is_not(None), last_run.error_summary != ""), last_run.error_summary),
            else_=func.coalesce(last_run.error_message, ""),
        )

        filters = []
        if query.company_id is not None:
            filters.append(CrawlerTask.company_id == query.company_id)
        if query.project_id is not None:
            filters.append(CrawlerTask.project_id == query.project_id)
        if query.task_name:
            filters.append(CrawlerTask.task_name.like(f"%{query.task_name}%"))
        if query.task_code:
            filters.append(CrawlerTask.task_code.like(f"%{query.task_code}%"))
        if query.entry_keyword:
            filters.append(or_(CrawlerTask.entry_module.like(f"%{query.entry_keyword}%"), CrawlerTask.entry_function.like(f"%{query.entry_keyword}%")))
        if query.task_group:
            filters.append(CrawlerTask.task_group.like(f"%{query.task_group}%"))
        if query.task_platform:
            filters.append(or_(CrawlerProject.project_name.like(f"%{query.task_platform}%"), CrawlerTask.task_group.like(f"%{query.task_platform}%")))
        if query.task_status:
            filters.append(CrawlerTask.status == query.task_status)
        else:
            filters.append(CrawlerTask.status != "ARCHIVED")
        if query.schedule_status:
            if query.schedule_status == "NONE":
                filters.append(CrawlerTaskSchedule.schedule_id.is_(None))
            else:
                filters.append(CrawlerTaskSchedule.schedule_status == query.schedule_status)
        if query.last_run_status:
            if query.last_run_status == "NOT_RUN":
                filters.append(last_run.run_id.is_(None))
            else:
                filters.append(last_run.run_status == query.last_run_status)
        if query.owner_user_id is not None:
            filters.append(CrawlerTask.owner_user_id == query.owner_user_id)
        if query.server_id is not None:
            filters.append(
                or_(
                    last_run.server_id == query.server_id,
                    exists(
                        select(1).where(
                            CrawlerTaskServerTarget.task_id == CrawlerTask.task_id,
                            CrawlerTaskServerTarget.server_id == query.server_id,
                            CrawlerTaskServerTarget.enabled.is_(True),
                        )
                    ),
                    exists(
                        select(1).where(
                            CrawlerProjectServer.project_id == CrawlerTask.project_id,
                            CrawlerProjectServer.server_id == query.server_id,
                            CrawlerProjectServer.deployment_status == "DEPLOYED",
                            CrawlerProjectServer.scheduling_status.notin_(["DISABLED", "DRAINING"]),
                        )
                    ),
                )
            )
        if member_user_id is not None:
            filters.append(
                exists(
                    select(1).where(
                        CrawlerProjectMember.project_id == CrawlerTask.project_id,
                        CrawlerProjectMember.user_id == member_user_id,
                    )
                )
            )

        from_clause = (
            CrawlerTask.__table__
            .join(CrawlerProject.__table__, CrawlerProject.project_id == CrawlerTask.project_id)
            .join(CrawlerCompany.__table__, CrawlerCompany.company_id == CrawlerTask.company_id)
            .outerjoin(CrawlerTaskSchedule.__table__, CrawlerTaskSchedule.task_id == CrawlerTask.task_id)
            .outerjoin(latest_run_ids, latest_run_ids.c.task_id == CrawlerTask.task_id)
            .outerjoin(last_run, last_run.run_id == latest_run_ids.c.last_run_id)
            .outerjoin(CrawlerServer.__table__, CrawlerServer.server_id == display_server_id)
            .outerjoin(SysUser.__table__, SysUser.user_id == CrawlerTask.owner_user_id)
        )

        columns = [
            CrawlerTask.task_id.label("task_id"),
            CrawlerTask.company_id.label("company_id"),
            CrawlerCompany.company_name.label("company_name"),
            CrawlerTask.project_id.label("project_id"),
            CrawlerProject.project_name.label("project_name"),
            CrawlerTask.task_code.label("task_code"),
            CrawlerTask.task_name.label("task_name"),
            CrawlerTask.task_group.label("task_group"),
            CrawlerTask.entry_module.label("entry_module"),
            CrawlerTask.entry_function.label("entry_function"),
            display_server_id.label("server_id"),
            CrawlerServer.server_name.label("server_name"),
            CrawlerServer.server_code.label("server_code"),
            CrawlerServer.server_ip.label("server_ip"),
            CrawlerTask.owner_user_id.label("owner_user_id"),
            owner_name.label("owner_user_name"),
            CrawlerTask.status.label("task_status"),
            CrawlerTaskSchedule.schedule_id.label("schedule_id"),
            CrawlerTaskSchedule.schedule_status.label("schedule_status"),
            CrawlerTaskSchedule.schedule_type.label("schedule_type"),
            CrawlerTaskSchedule.cron_expression.label("cron_expression"),
            CrawlerTaskSchedule.schedule_timezone.label("schedule_timezone"),
            CrawlerTaskSchedule.overlap_policy.label("overlap_policy"),
            CrawlerTaskSchedule.schedule_config.label("schedule_config"),
            CrawlerTaskSchedule.schedule_label.label("schedule_label"),
            CrawlerTaskSchedule.next_run_at.label("next_run_at"),
            last_run.run_id.label("last_run_id"),
            last_run.run_status.label("last_run_status"),
            last_run.routing_status.label("routing_status"),
            last_run.finished_at.label("last_finished_at"),
            error_summary.label("last_error_summary"),
            CrawlerTask.created_at.label("created_at"),
            CrawlerTask.updated_at.label("updated_at"),
        ]

        filtered_ids = select(CrawlerTask.task_id).select_from(from_clause).where(*filters).subquery("panel_filtered_ids")
        total = int(self.db.scalar(select(func.count()).select_from(filtered_ids)) or 0)
        stmt = (
            select(*columns)
            .select_from(from_clause)
            .where(*filters)
            .order_by(CrawlerTask.updated_at.desc(), CrawlerTask.task_id.desc())
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        rows = [dict(row) for row in self.db.execute(stmt).mappings().all()]
        return rows, total
