from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CrawlerProject
from app.schemas import BootstrapPreflightReport, BootstrapReleaseImport
from app.services.bootstrap_service import import_project_entries, verify_project_bootstrap_token, write_deployment_log
from app.services.project_manifest import ProjectManifestError
from app.services.release_service import ReleaseValidationError, import_release

router = APIRouter(prefix="/bootstrap", tags=["项目接入"])


def require_bootstrap_token(
    x_project_bootstrap_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not x_project_bootstrap_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 Project Bootstrap Token")
    token = verify_project_bootstrap_token(db, x_project_bootstrap_token.strip())
    if not token:
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Project Bootstrap Token 无效或已过期")
    return token


@router.get("/context")
def bootstrap_context(token=Depends(require_bootstrap_token), db: Session = Depends(get_db)) -> dict:
    project = db.get(CrawlerProject, token.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    db.commit()
    return {
        "company_id": token.company_id,
        "project_id": project.project_id,
        "project_code": project.project_code,
        "project_name": project.project_name,
        "registry": project.registry,
        "repository": project.repository,
        "default_branch": project.default_branch,
        "min_agent_version": project.min_agent_version,
        "allowed_repo": token.allowed_repo,
        "permissions": token.permissions_json,
    }


@router.post("/preflight")
def report_preflight(
    payload: BootstrapPreflightReport,
    token=Depends(require_bootstrap_token),
    db: Session = Depends(get_db),
) -> dict:
    row = write_deployment_log(
        db,
        token_row=token,
        stage=payload.stage,
        status=payload.status,
        message=payload.message,
        server_code=payload.server_code,
        agent_code=payload.agent_code,
        git_branch=payload.git_branch,
        git_commit=payload.git_commit,
        preflight=payload.checks,
    )
    db.commit()
    return {"deployment_id": row.deployment_id, "status": row.status}


@router.post("/spider-release")
def bootstrap_register_release(
    payload: BootstrapReleaseImport,
    token=Depends(require_bootstrap_token),
    db: Session = Depends(get_db),
) -> dict:
    project = db.get(CrawlerProject, token.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    expected_repo = f"{project.registry}/{project.repository}".strip("/")
    payload_repo = payload.image_repository.strip().rstrip("/")
    allowed_repo = (token.allowed_repo or expected_repo).strip().rstrip("/")
    if payload_repo != allowed_repo:
        raise HTTPException(status_code=403, detail="当前 token 不允许登记该镜像仓库")
    try:
        release = import_release(
            db,
            image_repository=payload.image_repository,
            image_tag=payload.image_tag,
            image_digest=payload.image_digest,
            git_commit=payload.git_commit,
            manifest=payload.manifest,
        )
    except ReleaseValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    import_result = {"imported": [], "skipped": [], "failed": []}
    if payload.import_entries and payload.project_manifest:
        try:
            import_result = import_project_entries(db, project=project, release=release, project_manifest=payload.project_manifest)
        except ProjectManifestError as exc:
            import_result = {"imported": [], "skipped": [], "failed": [{"reason": "PROJECT_MANIFEST_ERROR", "message": str(exc)}]}
    log = write_deployment_log(
        db,
        token_row=token,
        stage="REGISTER_RELEASE",
        status="SUCCESS" if not import_result["failed"] else "WARN",
        message="项目版本已登记；真实调度仍以前端平台配置为准",
        server_code=payload.server_code,
        agent_code=payload.agent_code,
        git_branch=payload.git_branch,
        git_commit=payload.git_commit,
        image_repository=payload.image_repository,
        image_digest=payload.image_digest,
        release_id=release.release_id,
        preflight=payload.preflight,
        result={"release_id": release.release_id, "entry_import": import_result},
    )
    db.commit()
    return {
        "deployment_id": log.deployment_id,
        "release_id": release.release_id,
        "version": release.version,
        "published_at": release.published_at,
        "entry_import": import_result,
        "message": "发布成功。重复任务已跳过；生产调度未被修改。",
    }
