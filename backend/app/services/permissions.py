from __future__ import annotations

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import CrawlerProject, CrawlerProjectMember, SysUser

PROJECT_RANK = {"VIEWER": 10, "OPERATOR": 20, "OWNER": 30}


def is_super_admin(user: SysUser) -> bool:
    return user.role_type == "SUPER_ADMIN"


def require_super_admin(user: SysUser) -> None:
    if not is_super_admin(user):
        raise AppError("仅超级管理员可执行此操作", code=40301, http_status=status.HTTP_403_FORBIDDEN)


def scoped_company_id(user: SysUser, requested_company_id: int | None = None) -> int | None:
    """Return the only company a normal user may access.

    Super admins may optionally scope to a requested company. Normal users can never
    widen or switch company by editing companyId in a request; cross-company access
    is deliberately returned as 404 to avoid leaking company existence.
    """
    if is_super_admin(user):
        return requested_company_id
    if not user.company_id:
        raise AppError("普通用户未绑定归属公司", code=40302, http_status=status.HTTP_403_FORBIDDEN)
    if requested_company_id is not None and requested_company_id != user.company_id:
        raise AppError("资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
    return user.company_id


def writable_company_id(user: SysUser, requested_company_id: int | None = None) -> int:
    scoped = scoped_company_id(user, requested_company_id)
    if scoped is None:
        raise AppError("请选择公司", code=40081)
    return scoped


def require_company_scope(user: SysUser, company_id: int) -> None:
    if is_super_admin(user):
        return
    if not user.company_id or user.company_id != company_id:
        raise AppError("资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)


def project_role(db: Session, user: SysUser, project_id: int) -> str | None:
    if is_super_admin(user):
        return "OWNER"
    project = db.get(CrawlerProject, project_id)
    if not project:
        return None
    if user.company_id and project.company_id == user.company_id:
        # 1.0.27 keeps a simple two-layer model: SUPER_ADMIN is global;
        # normal users are company-scoped operators for their own company.
        return "OWNER"
    row_role = db.scalar(select(CrawlerProjectMember.role).where(CrawlerProjectMember.project_id == project_id, CrawlerProjectMember.user_id == user.user_id))
    return row_role


def require_project_role(db: Session, user: SysUser, project_id: int, minimum: str = "VIEWER") -> CrawlerProject:
    project = db.get(CrawlerProject, project_id)
    if not project:
        raise AppError("资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
    require_company_scope(user, project.company_id)
    role = project_role(db, user, project_id)
    if not role or PROJECT_RANK.get(role, 0) < PROJECT_RANK[minimum]:
        raise AppError("无权访问该项目", code=40303, http_status=status.HTTP_403_FORBIDDEN)
    return project
