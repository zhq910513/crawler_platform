from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.services.cicd_service import CicdGuideService, render_init_script, render_workflow_template
from app.services.system_config_service import SystemConfigService

router = APIRouter(tags=["CI/CD"])
ROOT = Path(__file__).resolve().parents[3]


def _read_cicd_file(name: str) -> str:
    path = ROOT / "cicd" / name
    return path.read_text(encoding="utf-8")


def _detected_base(db: Session, request: Request, explicit: str = "") -> str:
    if explicit:
        return explicit.strip().rstrip("/")
    return SystemConfigService.detected_base_url_from_request(request)


@router.get("/cicd/spider-release-register.py")
def get_spider_release_register_script():
    return PlainTextResponse(_read_cicd_file("spider_release_register.py"), media_type="text/x-python; charset=utf-8")


@router.get("/cicd/spider-project-init.sh")
def get_spider_project_init_script(request: Request, provider: str = Query(default="github", pattern="^(github|gitlab)$"), company_code: str = Query(default="", alias="companyCode"), detected_base_url: str = Query(default="", alias="detectedBaseUrl"), db: Session = Depends(get_db)):
    detected = _detected_base(db, request, detected_base_url)
    control_base_url = SystemConfigService(db).resolve_control_plane_public_base_url(detected)
    script = render_init_script(_read_cicd_file("spider_project_init.sh"), control_base_url=control_base_url, provider=provider, company_code=company_code)
    return PlainTextResponse(script, media_type="text/x-shellscript; charset=utf-8")


@router.get("/cicd/templates/github-actions-spider-release.yml")
def get_github_actions_spider_release_template(request: Request, detected_base_url: str = Query(default="", alias="detectedBaseUrl"), db: Session = Depends(get_db)):
    control_base_url = SystemConfigService(db).resolve_control_plane_public_base_url(_detected_base(db, request, detected_base_url))
    return PlainTextResponse(render_workflow_template(_read_cicd_file("github-actions-spider-release.yml"), control_base_url), media_type="text/yaml; charset=utf-8")


@router.get("/cicd/templates/gitlab-ci-spider-release.yml")
def get_gitlab_ci_spider_release_template(request: Request, detected_base_url: str = Query(default="", alias="detectedBaseUrl"), db: Session = Depends(get_db)):
    control_base_url = SystemConfigService(db).resolve_control_plane_public_base_url(_detected_base(db, request, detected_base_url))
    return PlainTextResponse(render_workflow_template(_read_cicd_file("gitlab-ci-spider-release.yml"), control_base_url), media_type="text/yaml; charset=utf-8")


@router.get("/cicd/spider-projects/one-click-guide")
def get_spider_project_one_click_guide(request: Request, provider: str = Query(default="github", pattern="^(github|gitlab)$"), company_id: int | None = Query(default=None, alias="companyId"), detected_base_url: str = Query(default="", alias="detectedBaseUrl"), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    detected = detected_base_url or SystemConfigService.detected_base_url_from_request(request)
    return ok(CicdGuideService(db).spider_project_one_click_guide(user, provider=provider, company_id=company_id, detected_base_url=detected))
