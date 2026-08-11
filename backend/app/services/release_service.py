from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import CrawlerProjectRelease, SysUser
from app.repositories.platform import ReleaseRepository
from app.services.permissions import is_super_admin, require_project_role, scoped_company_id


class ReleaseService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ReleaseRepository(db)

    def list_releases(self, user: SysUser, company_id: int | None = None, project_id: int | None = None) -> list[CrawlerProjectRelease]:
        if project_id:
            project = require_project_role(self.db, user, project_id, "VIEWER")
            return self.repo.list_releases(project.company_id, project.project_id)
        if is_super_admin(user):
            return self.repo.list_releases(company_id)
        scoped = scoped_company_id(user, company_id)
        return self.repo.list_releases(scoped)
