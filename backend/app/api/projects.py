from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import (
    CrawlerCompanyMember,
    CrawlerProject,
    CrawlerProjectMember,
    CrawlerReleaseChannel,
    CrawlerSpiderEntry,
    CrawlerSpiderRelease,
    CrawlerTask,
    SysUser,
)
from app.schemas import ProjectCreate, ProjectMemberUpsert, ReleaseChannelUpdate
from app.services.audit import write_operation_log
from app.services.permissions import is_super_admin, project_role, require_company_role, require_project_role, visible_project_ids

router = APIRouter(prefix="/projects", tags=["项目"])


def project_dict(db: Session, row: CrawlerProject, user: SysUser) -> dict:
    return {
        "project_id": row.project_id,
        "company_id": row.company_id,
        "project_code": row.project_code,
        "project_name": row.project_name,
        "registry": row.registry,
        "repository": row.repository,
        "default_branch": row.default_branch,
        "status": row.status,
        "description": row.description,
        "role": project_role(db, user, row.project_id),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("")
def list_projects(
    company_id: int | None = None,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> list[dict]:
    stmt = select(CrawlerProject).order_by(CrawlerProject.project_id.desc())
    if company_id:
        stmt = stmt.where(CrawlerProject.company_id == company_id)
    ids = visible_project_ids(db, user)
    if ids is not None:
        stmt = stmt.where(CrawlerProject.project_id.in_(ids or [-1]))
    return [project_dict(db, row, user) for row in db.scalars(stmt).all()]


@router.get("/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db), user: SysUser = Depends(get_current_user)) -> dict:
    require_project_role(db, user, project_id, "VIEWER")
    row = db.get(CrawlerProject, project_id)
    return project_dict(db, row, user)


@router.post("")
def create_project(
    payload: ProjectCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    require_company_role(db, user, payload.company_id, "ADMIN")
    if db.scalar(select(CrawlerProject).where(CrawlerProject.project_code == payload.project_code)):
        raise HTTPException(status_code=409, detail="项目编码已存在")
    row = CrawlerProject(**payload.model_dump(), created_by=user.user_id)
    db.add(row)
    db.flush()
    db.add(CrawlerProjectMember(project_id=row.project_id, user_id=user.user_id, role="OWNER"))
    write_operation_log(db, request, user, "CREATE", "PROJECT", row.project_id, after_data=payload.model_dump())
    db.commit()
    return project_dict(db, row, user)


@router.put("/{project_id}")
def update_project(
    project_id: int,
    payload: ProjectCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    require_project_role(db, user, project_id, "OWNER")
    row = db.get(CrawlerProject, project_id)
    if row.company_id != payload.company_id:
        raise HTTPException(status_code=409, detail="项目不能跨公司迁移")
    duplicate = db.scalar(select(CrawlerProject).where(CrawlerProject.project_code == payload.project_code, CrawlerProject.project_id != project_id))
    if duplicate:
        raise HTTPException(status_code=409, detail="项目编码已存在")
    before = project_dict(db, row, user)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    write_operation_log(db, request, user, "UPDATE", "PROJECT", project_id, before_data=before, after_data=payload.model_dump())
    db.commit()
    return project_dict(db, row, user)


@router.get("/{project_id}/members")
def list_members(project_id: int, db: Session = Depends(get_db), user: SysUser = Depends(get_current_user)) -> list[dict]:
    require_project_role(db, user, project_id, "VIEWER")
    rows = db.execute(
        select(CrawlerProjectMember, SysUser)
        .join(SysUser, SysUser.user_id == CrawlerProjectMember.user_id)
        .where(CrawlerProjectMember.project_id == project_id)
        .order_by(CrawlerProjectMember.member_id)
    ).all()
    return [{"user_id": account.user_id, "user_name": account.user_name, "nick_name": account.nick_name, "role": member.role} for member, account in rows]


@router.put("/{project_id}/members")
def upsert_member(
    project_id: int,
    payload: ProjectMemberUpsert,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    require_project_role(db, user, project_id, "OWNER")
    project = db.get(CrawlerProject, project_id)
    company_member = db.scalar(select(func.count()).select_from(CrawlerCompanyMember).where(
        CrawlerCompanyMember.company_id == project.company_id,
        CrawlerCompanyMember.user_id == payload.user_id,
    )) or 0
    if not company_member:
        raise HTTPException(status_code=409, detail="只能添加所属公司的成员")
    row = db.scalar(select(CrawlerProjectMember).where(
        CrawlerProjectMember.project_id == project_id,
        CrawlerProjectMember.user_id == payload.user_id,
    ))
    if row:
        row.role = payload.role
    else:
        db.add(CrawlerProjectMember(project_id=project_id, user_id=payload.user_id, role=payload.role))
    write_operation_log(db, request, user, "UPSERT_MEMBER", "PROJECT", project_id, after_data=payload.model_dump())
    db.commit()
    return {"ok": True}


@router.delete("/{project_id}/members/{user_id}")
def delete_member(
    project_id: int,
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    require_project_role(db, user, project_id, "OWNER")
    row = db.scalar(select(CrawlerProjectMember).where(
        CrawlerProjectMember.project_id == project_id,
        CrawlerProjectMember.user_id == user_id,
    ))
    if not row:
        raise HTTPException(status_code=404, detail="项目成员不存在")
    if row.role == "OWNER":
        owners = db.scalar(select(func.count()).select_from(CrawlerProjectMember).where(
            CrawlerProjectMember.project_id == project_id,
            CrawlerProjectMember.role == "OWNER",
        )) or 0
        if owners <= 1:
            raise HTTPException(status_code=409, detail="项目至少保留一名 OWNER")
    db.delete(row)
    write_operation_log(db, request, user, "DELETE_MEMBER", "PROJECT", project_id, before_data={"user_id": user_id})
    db.commit()
    return {"ok": True}


def _channel_dict(db: Session, row: CrawlerReleaseChannel) -> dict:
    release = db.get(CrawlerSpiderRelease, row.spider_release_id) if row.spider_release_id else None
    return {
        "channel_id": row.channel_id,
        "project_id": row.project_id,
        "channel_name": row.channel_name,
        "spider_release_id": row.spider_release_id,
        "version": release.version if release else None,
        "image_digest": release.image_digest if release else None,
    }


@router.get("/{project_id}/channels")
def list_channels(project_id: int, db: Session = Depends(get_db), user: SysUser = Depends(get_current_user)) -> list[dict]:
    require_project_role(db, user, project_id, "VIEWER")
    rows = db.scalars(select(CrawlerReleaseChannel).where(CrawlerReleaseChannel.project_id == project_id).order_by(CrawlerReleaseChannel.channel_name)).all()
    return [_channel_dict(db, row) for row in rows]


@router.put("/{project_id}/channels/{channel_name}")
def set_channel(
    project_id: int,
    channel_name: str,
    payload: ReleaseChannelUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    require_project_role(db, user, project_id, "OWNER")
    release = db.get(CrawlerSpiderRelease, payload.spider_release_id)
    if not release or release.status != "ACTIVE":
        raise HTTPException(status_code=400, detail="SpiderRelease 不可用")
    row = db.scalar(select(CrawlerReleaseChannel).where(
        CrawlerReleaseChannel.project_id == project_id,
        CrawlerReleaseChannel.channel_name == channel_name,
    ))
    if row:
        row.spider_release_id = release.release_id
    else:
        row = CrawlerReleaseChannel(project_id=project_id, channel_name=channel_name, spider_release_id=release.release_id)
        db.add(row)
    db.flush()
    write_operation_log(db, request, user, "SET_CHANNEL", "PROJECT", project_id, after_data={"channel": channel_name, "spider_release_id": release.release_id})
    db.commit()
    return _channel_dict(db, row)


@router.post("/{project_id}/channels/{channel_name}/rollback")
def rollback_channel(
    project_id: int,
    channel_name: str,
    payload: ReleaseChannelUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    # 回滚本质是显式切换，但保留独立审计操作名。
    require_project_role(db, user, project_id, "OWNER")
    release = db.get(CrawlerSpiderRelease, payload.spider_release_id)
    if not release or release.status != "ACTIVE":
        raise HTTPException(status_code=400, detail="目标版本不可用")
    required_names = set(db.scalars(select(CrawlerTask.spider_task_name).where(
        CrawlerTask.project_id == project_id,
        CrawlerTask.status == "ENABLED",
    )).all())
    available = set(db.scalars(select(CrawlerSpiderEntry.task_name).where(CrawlerSpiderEntry.release_id == release.release_id)).all())
    missing = sorted(required_names - available)
    if missing:
        raise HTTPException(status_code=409, detail={"message": "目标版本缺少项目正在使用的入口", "missing_entries": missing})
    row = db.scalar(select(CrawlerReleaseChannel).where(CrawlerReleaseChannel.project_id == project_id, CrawlerReleaseChannel.channel_name == channel_name))
    if not row:
        row = CrawlerReleaseChannel(project_id=project_id, channel_name=channel_name)
        db.add(row)
    before = row.spider_release_id
    row.spider_release_id = release.release_id
    write_operation_log(db, request, user, "ROLLBACK_RELEASE", "PROJECT", project_id, before_data={"release_id": before}, after_data={"release_id": release.release_id})
    db.commit()
    return _channel_dict(db, row)
