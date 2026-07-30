from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CrawlerCompanyMember, CrawlerProject, CrawlerProjectMember, SysUser

PROJECT_RANK = {"VIEWER": 10, "OPERATOR": 20, "OWNER": 30}
COMPANY_RANK = {"MEMBER": 10, "ADMIN": 20, "OWNER": 30}


def is_super_admin(user: SysUser) -> bool:
    return user.role_type == "SUPER_ADMIN"


def visible_project_ids(db: Session, user: SysUser) -> list[int] | None:
    if is_super_admin(user):
        return None
    return list(db.scalars(select(CrawlerProjectMember.project_id).where(CrawlerProjectMember.user_id == user.user_id)).all())


def project_role(db: Session, user: SysUser, project_id: int) -> str | None:
    if is_super_admin(user):
        return "OWNER"
    return db.scalar(
        select(CrawlerProjectMember.role).where(
            CrawlerProjectMember.project_id == project_id,
            CrawlerProjectMember.user_id == user.user_id,
        )
    )


def require_project_role(db: Session, user: SysUser, project_id: int, minimum: str = "VIEWER") -> str:
    project = db.get(CrawlerProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    role = project_role(db, user, project_id)
    if not role or PROJECT_RANK.get(role, 0) < PROJECT_RANK[minimum]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该项目")
    return role


def company_role(db: Session, user: SysUser, company_id: int) -> str | None:
    if is_super_admin(user):
        return "OWNER"
    return db.scalar(
        select(CrawlerCompanyMember.role).where(
            CrawlerCompanyMember.company_id == company_id,
            CrawlerCompanyMember.user_id == user.user_id,
        )
    )


def require_company_role(db: Session, user: SysUser, company_id: int, minimum: str = "MEMBER") -> str:
    role = company_role(db, user, company_id)
    if not role or COMPANY_RANK.get(role, 0) < COMPANY_RANK[minimum]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该公司")
    return role
