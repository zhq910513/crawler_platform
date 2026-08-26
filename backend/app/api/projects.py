from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.schemas import ProjectBuildCancel, ProjectBuildCreate, ProjectDiscoveryCreate, ProjectImport, ProjectPublishPipelineRequest, ProjectReleaseDeploy, ProjectServerPoolUpdate, ProjectUpdate
from app.services.project_service import ProjectService
from app.services.build_center_service import BuildCenterService

router = APIRouter(tags=["项目"])


@router.get("/discovered-projects")
def list_discovered_projects(company_id: int | None = Query(default=None), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ProjectService(db).list_discovered(user, company_id))


@router.post("/discovered-projects")
def create_discovered_project(payload: ProjectDiscoveryCreate, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    service = ProjectService(db)
    service.validate_discovery_token(payload, authorization)
    return ok(service.upsert_discovered(payload))


@router.get("/project-builds")
def list_project_build_jobs(company_id: int | None = Query(default=None), limit: int = Query(default=50, ge=1, le=200), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    # Build jobs are company scoped. The list endpoint intentionally exposes only
    # platform-created build records; it does not trigger repository access.
    if company_id is not None:
        from app.services.permissions import require_company_scope
        require_company_scope(user, company_id)
    return ok(BuildCenterService(db).list_jobs(company_id, limit))


@router.get("/project-builds/{build_job_id}")
def get_project_build_job(build_job_id: int, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    payload = BuildCenterService(db).get_job(build_job_id)
    from app.services.permissions import require_company_scope
    require_company_scope(user, int(payload["company_id"]))
    return ok(payload)


@router.post("/project-builds")
def create_project_build_job(payload: ProjectBuildCreate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.permissions import require_company_scope
    require_company_scope(user, payload.company_id)
    job = BuildCenterService(db).start_project_release_build(user, payload.company_id, payload.repository_url, payload.ref_name)
    return ok({"buildJob": BuildCenterService(db).get_job(job.build_job_id), "message": "构建任务已在后台启动；请轮询 /project-builds/{buildJobId} 获取阶段和日志。"})


@router.post("/project-builds/{build_job_id}/cancellations")
def cancel_project_build_job(build_job_id: int, payload: ProjectBuildCancel | None = None, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    service = BuildCenterService(db)
    current = service.get_job(build_job_id, auto_resume=False)
    from app.services.permissions import require_company_scope
    require_company_scope(user, int(current["company_id"]))
    job = service.cancel_project_release_build(build_job_id, payload.reason if payload else "用户取消构建")
    return ok({"buildJob": service.get_job(job.build_job_id), "message": "构建任务已取消；如需再次发布可点击重新构建。"})


@router.post("/project-builds/{build_job_id}/retries")
def retry_project_build_job(build_job_id: int, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    service = BuildCenterService(db)
    current = service.get_job(build_job_id, auto_resume=False)
    from app.services.permissions import require_company_scope
    require_company_scope(user, int(current["company_id"]))
    job = service.retry_project_release_build(user, build_job_id)
    return ok({"buildJob": service.get_job(job.build_job_id), "message": "构建任务已重新入队；页面将继续轮询新任务状态。"})




@router.post("/project-source-bundles")
async def upload_project_source_bundle(
    company_id: int = Form(...),
    repository_url: str = Form(...),
    ref_name: str = Form("main"),
    file: UploadFile = File(...),
    user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.permissions import require_company_scope
    require_company_scope(user, company_id)
    content = await file.read()
    result = BuildCenterService(db).save_source_bundle(user, company_id, repository_url, ref_name, file.filename or "source.zip", content)
    return ok({"sourceBundle": result, "message": "源码包已上传；可点击重新构建，平台会在 GitHub 不可用时自动使用该源码包兜底。"})


@router.get("/projects")
def list_projects(company_id: int | None = Query(default=None), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ProjectService(db).list_projects(user, company_id))


@router.post("/project-publish/pipeline-analyses")
def analyze_project_publish_pipeline(payload: ProjectPublishPipelineRequest, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ProjectService(db).analyze_publish_pipeline(user, payload))


@router.post("/project-publish/pipelines")
def run_project_publish_pipeline(payload: ProjectPublishPipelineRequest, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ProjectService(db).run_publish_pipeline(user, payload))


@router.post("/projects")
def import_project(payload: ProjectImport, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ProjectService(db).import_project(user, payload))


@router.get("/projects/{project_id}")
def get_project(project_id: int, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ProjectService(db).get_project(user, project_id))


@router.patch("/projects/{project_id}")
def update_project(project_id: int, payload: ProjectUpdate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ProjectService(db).update_project(user, project_id, payload))


@router.delete("/projects/{project_id}")
def delete_project(project_id: int, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ProjectService(db).delete_project(user, project_id))


@router.get("/projects/{project_id}/servers")
def list_project_servers(project_id: int, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ProjectService(db).list_project_servers(user, project_id))


@router.post("/projects/{project_id}/server-pool-analyses")
def create_project_server_pool_analysis(project_id: int, payload: ProjectServerPoolUpdate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ProjectService(db).analyze_server_pool(user, project_id, payload))


@router.put("/projects/{project_id}/servers")
def update_project_servers(project_id: int, payload: ProjectServerPoolUpdate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ProjectService(db).update_server_pool(user, project_id, payload))


@router.post("/projects/{project_id}/release-deployments")
def deploy_project_release(project_id: int, payload: ProjectReleaseDeploy, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ProjectService(db).deploy_release_to_servers(user, project_id, payload))


@router.get("/projects/{project_id}/release-deployments")
def list_project_release_deployments(project_id: int, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ProjectService(db).list_deployments(user, project_id))
