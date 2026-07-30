from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, verify_cicd_token
from app.models import CrawlerReleaseChannel, CrawlerSpiderEntry, CrawlerSpiderRelease, CrawlerTask, CrawlerTaskRun, CrawlerTaskRuntime, SysUser
from app.schemas import SpiderReleaseImport
from app.services.permissions import is_super_admin
from app.services.release_service import ReleaseValidationError, import_release
from app.services.run_state import TERMINAL_STATUSES

router = APIRouter(prefix="/spider-releases", tags=["爬虫发布"])
cicd_router = APIRouter(prefix="/cicd", tags=["CI/CD"])


def entry_dict(row: CrawlerSpiderEntry) -> dict:
    return {
        "entry_id": row.entry_id,
        "release_id": row.release_id,
        "task_name": row.task_name,
        "display_name": row.display_name,
        "description": row.description,
        "image_profile": row.image_profile,
        "parameter_schema": row.parameter_schema,
        "required_resources": row.required_resources,
        "default_timeout_seconds": row.default_timeout_seconds,
    }


def release_dict(db: Session, row: CrawlerSpiderRelease, include_entries: bool = False) -> dict:
    result = {
        "release_id": row.release_id,
        "app_name": row.app_name,
        "version": row.version,
        "image_repository": row.image_repository,
        "image_tag": row.image_tag,
        "image_digest": row.image_digest,
        "git_commit": row.git_commit,
        "status": row.status,
        "published_at": row.published_at,
        "created_at": row.created_at,
    }
    if include_entries:
        entries = db.scalars(select(CrawlerSpiderEntry).where(CrawlerSpiderEntry.release_id == row.release_id).order_by(CrawlerSpiderEntry.task_name)).all()
        result["entries"] = [entry_dict(item) for item in entries]
    return result


@router.get("")
def list_releases(db: Session = Depends(get_db), user: SysUser = Depends(get_current_user)) -> list[dict]:
    rows = db.scalars(select(CrawlerSpiderRelease).order_by(CrawlerSpiderRelease.release_id.desc())).all()
    return [release_dict(db, row) for row in rows]


@router.get("/{release_id}")
def get_release(release_id: int, db: Session = Depends(get_db), user: SysUser = Depends(get_current_user)) -> dict:
    row = db.get(CrawlerSpiderRelease, release_id)
    if not row:
        raise HTTPException(status_code=404, detail="发布版本不存在")
    return release_dict(db, row, include_entries=True)


@router.patch("/{release_id}/status")
def update_release_status(
    release_id: int,
    status: str,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="仅超级管理员可调整发布状态")
    if status not in {"ACTIVE", "DISABLED"}:
        raise HTTPException(status_code=400, detail="状态必须为 ACTIVE 或 DISABLED")
    row = db.get(CrawlerSpiderRelease, release_id)
    if not row:
        raise HTTPException(status_code=404, detail="发布版本不存在")
    if status == "DISABLED":
        channel_count = db.scalar(select(func.count()).select_from(CrawlerReleaseChannel).where(CrawlerReleaseChannel.spider_release_id == release_id)) or 0
        task_count = db.scalar(select(func.count()).select_from(CrawlerTaskRuntime).where(CrawlerTaskRuntime.fixed_spider_release_id == release_id)) or 0
        active_run_count = db.scalar(select(func.count()).select_from(CrawlerTaskRun).where(
            CrawlerTaskRun.spider_release_id == release_id,
            ~CrawlerTaskRun.status.in_(TERMINAL_STATUSES),
        )) or 0
        if channel_count or task_count or active_run_count:
            raise HTTPException(status_code=409, detail="该版本仍被发布通道、固定任务或运行实例引用")
    row.status = status
    db.commit()
    return release_dict(db, row)


@cicd_router.post("/spider-releases", dependencies=[Depends(verify_cicd_token)])
def register_release(payload: SpiderReleaseImport, db: Session = Depends(get_db)) -> dict:
    try:
        row = import_release(
            db,
            image_repository=payload.image_repository,
            image_tag=payload.image_tag,
            image_digest=payload.image_digest,
            git_commit=payload.git_commit,
            manifest=payload.manifest,
        )
    except ReleaseValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return release_dict(db, row, include_entries=True)
