from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.schemas import ProjectBuildCreate, ProjectDiscoveryCreate, ProjectImport, ProjectPublishPipelineRequest, ProjectReleaseDeploy, ProjectServerPoolUpdate, ProjectUpdate
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
    manifest, job = BuildCenterService(db).build_project_release(user, payload.company_id, payload.repository_url, payload.ref_name)
    discovered = ProjectService(db).upsert_discovered(ProjectDiscoveryCreate(company_id=payload.company_id, manifest=manifest))
    job.discovered_project_id = discovered.discovered_project_id
    job.release_id = discovered.latest_release_id
    db.commit()
    return ok({"buildJob": BuildCenterService(db).get_job(job.build_job_id), "discoveredProject": ProjectService(db)._discovered_payload(discovered)})


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
