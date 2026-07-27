from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin, verify_cicd_token
from app.models import CrawlerImageVersion, CrawlerProject, CrawlerReleaseChannel, SysUser
from app.schemas import ImageVersionCreate, ProjectCreate
from app.services.audit import write_operation_log
from app.utils import utcnow

router = APIRouter(prefix="/projects", tags=["项目与镜像"])
cicd_router = APIRouter(prefix="/cicd", tags=["CI/CD"])


def project_dict(row: CrawlerProject) -> dict:
    return {
        "project_id": row.project_id,
        "project_code": row.project_code,
        "project_name": row.project_name,
        "registry": row.registry,
        "repository": row.repository,
        "default_branch": row.default_branch,
        "status": row.status,
        "description": row.description,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def image_dict(row: CrawlerImageVersion) -> dict:
    return {
        "image_version_id": row.image_version_id,
        "project_id": row.project_id,
        "image_tag": row.image_tag,
        "image_digest": row.image_digest,
        "git_branch": row.git_branch,
        "git_commit": row.git_commit,
        "pipeline_id": row.pipeline_id,
        "build_status": row.build_status,
        "build_url": row.build_url,
        "built_at": row.built_at,
        "created_at": row.created_at,
    }


@router.get("")
def list_projects(db: Session = Depends(get_db), _: SysUser = Depends(require_admin)) -> list[dict]:
    return [project_dict(row) for row in db.scalars(select(CrawlerProject).order_by(CrawlerProject.project_id.desc())).all()]


@router.post("")
def create_project(
    payload: ProjectCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(require_admin),
) -> dict:
    if db.scalar(select(CrawlerProject).where(CrawlerProject.project_code == payload.project_code)):
        raise HTTPException(status_code=409, detail="项目编码已存在")
    row = CrawlerProject(**payload.model_dump())
    db.add(row)
    db.flush()
    write_operation_log(db, request, user, "CREATE", "PROJECT", row.project_id, after_data=project_dict(row))
    db.commit()
    return project_dict(row)


@router.put("/{project_id}")
def update_project(
    project_id: int,
    payload: ProjectCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(require_admin),
) -> dict:
    row = db.get(CrawlerProject, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="项目不存在")
    before = project_dict(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    write_operation_log(db, request, user, "UPDATE", "PROJECT", row.project_id, before, project_dict(row))
    db.commit()
    return project_dict(row)


@router.get("/{project_id}/images")
def list_images(project_id: int, db: Session = Depends(get_db), _: SysUser = Depends(require_admin)) -> list[dict]:
    rows = db.scalars(
        select(CrawlerImageVersion)
        .where(CrawlerImageVersion.project_id == project_id)
        .order_by(CrawlerImageVersion.built_at.desc(), CrawlerImageVersion.image_version_id.desc())
    ).all()
    return [image_dict(row) for row in rows]


@router.put("/{project_id}/channels/{channel_name}")
def set_channel(
    project_id: int,
    channel_name: str,
    image_version_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(require_admin),
) -> dict:
    image = db.get(CrawlerImageVersion, image_version_id)
    if not image or image.project_id != project_id or image.build_status != "SUCCESS":
        raise HTTPException(status_code=400, detail="镜像版本不可用")
    row = db.scalar(
        select(CrawlerReleaseChannel).where(
            CrawlerReleaseChannel.project_id == project_id,
            CrawlerReleaseChannel.channel_name == channel_name,
        )
    )
    if row:
        row.image_version_id = image_version_id
    else:
        row = CrawlerReleaseChannel(project_id=project_id, channel_name=channel_name, image_version_id=image_version_id)
        db.add(row)
    db.flush()
    write_operation_log(db, request, user, "SET_CHANNEL", "PROJECT", project_id, after_data={"channel": channel_name, "image_version_id": image_version_id})
    db.commit()
    return {"project_id": project_id, "channel_name": channel_name, "image_version_id": image_version_id}


@cicd_router.post("/image-versions", dependencies=[Depends(verify_cicd_token)])
def register_image(payload: ImageVersionCreate, db: Session = Depends(get_db)) -> dict:
    project = db.scalar(select(CrawlerProject).where(CrawlerProject.project_code == payload.project_code))
    if not project:
        raise HTTPException(status_code=404, detail="项目编码不存在，请先在平台创建项目")
    row = db.scalar(
        select(CrawlerImageVersion).where(
            CrawlerImageVersion.project_id == project.project_id,
            CrawlerImageVersion.image_digest == payload.image_digest,
        )
    )
    values = payload.model_dump(exclude={"project_code"})
    values["built_at"] = values["built_at"] or utcnow()
    if row:
        for key, value in values.items():
            setattr(row, key, value)
    else:
        row = CrawlerImageVersion(project_id=project.project_id, **values)
        db.add(row)
    db.commit()
    db.refresh(row)
    return image_dict(row)
