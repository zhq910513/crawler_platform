from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.schemas import ProjectDiscoveryCreate, ProjectImport, ProjectPublishPipelineRequest, ProjectReleaseDeploy, ProjectServerPoolUpdate, ProjectUpdate
from app.services.project_service import ProjectService

router = APIRouter(tags=["项目"])


@router.get("/discovered-projects")
def list_discovered_projects(company_id: int | None = Query(default=None), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ProjectService(db).list_discovered(user, company_id))


@router.post("/discovered-projects")
def create_discovered_project(payload: ProjectDiscoveryCreate, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    service = ProjectService(db)
    service.validate_discovery_token(payload, authorization)
    return ok(service.upsert_discovered(payload))


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
