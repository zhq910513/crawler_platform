from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CrawlerAgent,
    CrawlerCompany,
    CrawlerDiscoveredProject,
    CrawlerDiscoveredProjectServer,
    CrawlerImageArtifact,
    CrawlerProject,
    CrawlerProjectMember,
    CrawlerProjectRelease,
    CrawlerProjectServer,
    CrawlerProjectTaskDefinition,
    CrawlerReleaseChannel,
    CrawlerRunLog,
    CrawlerServer,
    CrawlerTask,
    CrawlerTaskRun,
    CrawlerTaskSchedule,
    CrawlerTaskServerTarget,
    SysAlertEvent,
    SysNotificationChannel,
    SysOperationLog,
)
from app.repositories.base import BaseRepository


class CompanyRepository(BaseRepository[CrawlerCompany]):
    def __init__(self, db: Session):
        super().__init__(db, CrawlerCompany)

    def by_code(self, company_code: str) -> CrawlerCompany | None:
        return self.db.scalar(select(CrawlerCompany).where(CrawlerCompany.company_code == company_code))

    def list_companies(self) -> list[CrawlerCompany]:
        return list(self.db.scalars(select(CrawlerCompany).order_by(CrawlerCompany.created_at.desc())).all())


class ServerRepository(BaseRepository[CrawlerServer]):
    def __init__(self, db: Session):
        super().__init__(db, CrawlerServer)

    def by_code(self, server_code: str) -> CrawlerServer | None:
        return self.db.scalar(select(CrawlerServer).where(CrawlerServer.server_code == server_code))

    def list_servers(self, company_id: int | None = None) -> list[CrawlerServer]:
        stmt = select(CrawlerServer).order_by(CrawlerServer.created_at.desc())
        if company_id is not None:
            stmt = stmt.where(CrawlerServer.company_id == company_id)
        return list(self.db.scalars(stmt).all())


class AgentRepository(BaseRepository[CrawlerAgent]):
    def __init__(self, db: Session):
        super().__init__(db, CrawlerAgent)

    def by_token_hash(self, token_hash: str) -> CrawlerAgent | None:
        return self.db.scalar(select(CrawlerAgent).where(CrawlerAgent.token_hash == token_hash))

    def by_code(self, agent_code: str) -> CrawlerAgent | None:
        return self.db.scalar(select(CrawlerAgent).where(CrawlerAgent.agent_code == agent_code))


class DiscoveredProjectRepository(BaseRepository[CrawlerDiscoveredProject]):
    def __init__(self, db: Session):
        super().__init__(db, CrawlerDiscoveredProject)

    def by_company_key(self, company_id: int, project_key: str) -> CrawlerDiscoveredProject | None:
        return self.db.scalar(select(CrawlerDiscoveredProject).where(CrawlerDiscoveredProject.company_id == company_id, CrawlerDiscoveredProject.project_key == project_key))

    def list_projects(self, company_id: int | None = None) -> list[CrawlerDiscoveredProject]:
        stmt = select(CrawlerDiscoveredProject).order_by(CrawlerDiscoveredProject.last_deployed_at.desc().nullslast(), CrawlerDiscoveredProject.created_at.desc())
        if company_id is not None:
            stmt = stmt.where(CrawlerDiscoveredProject.company_id == company_id)
        return list(self.db.scalars(stmt).all())


class ProjectRepository(BaseRepository[CrawlerProject]):
    def __init__(self, db: Session):
        super().__init__(db, CrawlerProject)

    def list_projects(self, company_id: int | None = None, user_id: int | None = None) -> list[CrawlerProject]:
        stmt = select(CrawlerProject).order_by(CrawlerProject.created_at.desc())
        if company_id is not None:
            stmt = stmt.where(CrawlerProject.company_id == company_id)
        if user_id is not None:
            stmt = stmt.join(CrawlerProjectMember, CrawlerProjectMember.project_id == CrawlerProject.project_id).where(CrawlerProjectMember.user_id == user_id)
        return list(self.db.scalars(stmt).all())

    def by_company_code(self, company_id: int, project_code: str) -> CrawlerProject | None:
        return self.db.scalar(select(CrawlerProject).where(CrawlerProject.company_id == company_id, CrawlerProject.project_code == project_code))


class ProjectServerRepository(BaseRepository[CrawlerProjectServer]):
    def __init__(self, db: Session):
        super().__init__(db, CrawlerProjectServer)

    def list_by_project(self, project_id: int) -> list[CrawlerProjectServer]:
        return list(self.db.scalars(select(CrawlerProjectServer).where(CrawlerProjectServer.project_id == project_id).order_by(CrawlerProjectServer.priority.asc())).all())


class ReleaseRepository(BaseRepository[CrawlerProjectRelease]):
    def __init__(self, db: Session):
        super().__init__(db, CrawlerProjectRelease)

    def list_releases(self, company_id: int | None = None, project_id: int | None = None) -> list[CrawlerProjectRelease]:
        stmt = select(CrawlerProjectRelease).order_by(CrawlerProjectRelease.published_at.desc())
        if company_id is not None:
            stmt = stmt.where(CrawlerProjectRelease.company_id == company_id)
        if project_id is not None:
            stmt = stmt.where(CrawlerProjectRelease.project_id == project_id)
        return list(self.db.scalars(stmt).all())


class TaskDefinitionRepository(BaseRepository[CrawlerProjectTaskDefinition]):
    def __init__(self, db: Session):
        super().__init__(db, CrawlerProjectTaskDefinition)

    def by_project_key(self, project_id: int, definition_key: str) -> CrawlerProjectTaskDefinition | None:
        return self.db.scalar(select(CrawlerProjectTaskDefinition).where(CrawlerProjectTaskDefinition.project_id == project_id, CrawlerProjectTaskDefinition.definition_key == definition_key))

    def list_by_project(self, project_id: int) -> list[CrawlerProjectTaskDefinition]:
        return list(self.db.scalars(select(CrawlerProjectTaskDefinition).where(CrawlerProjectTaskDefinition.project_id == project_id).order_by(CrawlerProjectTaskDefinition.created_at.desc())).all())


class TaskRepository(BaseRepository[CrawlerTask]):
    def __init__(self, db: Session):
        super().__init__(db, CrawlerTask)

    def list_tasks(self, company_id: int | None = None, project_id: int | None = None, user_id: int | None = None) -> list[CrawlerTask]:
        stmt = select(CrawlerTask).order_by(CrawlerTask.created_at.desc())
        if company_id is not None:
            stmt = stmt.where(CrawlerTask.company_id == company_id)
        if project_id is not None:
            stmt = stmt.where(CrawlerTask.project_id == project_id)
        if user_id is not None:
            stmt = stmt.join(CrawlerProjectMember, CrawlerProjectMember.project_id == CrawlerTask.project_id).where(CrawlerProjectMember.user_id == user_id)
        return list(self.db.scalars(stmt).all())


class RunRepository(BaseRepository[CrawlerTaskRun]):
    def __init__(self, db: Session):
        super().__init__(db, CrawlerTaskRun)

    def list_runs(self, company_id: int | None = None, project_id: int | None = None, task_id: int | None = None, user_id: int | None = None) -> list[CrawlerTaskRun]:
        stmt = select(CrawlerTaskRun).order_by(CrawlerTaskRun.created_at.desc()).limit(500)
        if company_id is not None:
            stmt = stmt.where(CrawlerTaskRun.company_id == company_id)
        if project_id is not None:
            stmt = stmt.where(CrawlerTaskRun.project_id == project_id)
        if task_id is not None:
            stmt = stmt.where(CrawlerTaskRun.task_id == task_id)
        if user_id is not None:
            stmt = stmt.join(CrawlerProjectMember, CrawlerProjectMember.project_id == CrawlerTaskRun.project_id).where(CrawlerProjectMember.user_id == user_id)
        return list(self.db.scalars(stmt).all())


class NotificationRepository(BaseRepository[SysNotificationChannel]):
    def __init__(self, db: Session):
        super().__init__(db, SysNotificationChannel)

    def list_channels(self, company_id: int | None = None) -> list[SysNotificationChannel]:
        stmt = select(SysNotificationChannel).order_by(SysNotificationChannel.created_at.desc())
        if company_id is not None:
            stmt = stmt.where((SysNotificationChannel.company_id == company_id) | (SysNotificationChannel.scope_type == "SYSTEM"))
        return list(self.db.scalars(stmt).all())


__all__ = [
    "CompanyRepository",
    "ServerRepository",
    "AgentRepository",
    "DiscoveredProjectRepository",
    "ProjectRepository",
    "ProjectServerRepository",
    "ReleaseRepository",
    "TaskDefinitionRepository",
    "TaskRepository",
    "RunRepository",
    "NotificationRepository",
    "CrawlerDiscoveredProjectServer",
    "CrawlerImageArtifact",
    "CrawlerProjectMember",
    "CrawlerProjectServer",
    "CrawlerProjectRelease",
    "CrawlerReleaseChannel",
    "CrawlerProjectTaskDefinition",
    "CrawlerTask",
    "CrawlerTaskSchedule",
    "CrawlerTaskServerTarget",
    "CrawlerTaskRun",
    "CrawlerRunLog",
    "SysAlertEvent",
    "SysOperationLog",
]
