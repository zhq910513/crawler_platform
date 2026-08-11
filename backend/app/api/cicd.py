from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.services.cicd_service import CicdGuideService

router = APIRouter(tags=["CI/CD"])
ROOT = Path(__file__).resolve().parents[3]


def _read_cicd_file(name: str) -> str:
    path = ROOT / "cicd" / name
    return path.read_text(encoding="utf-8")


@router.get("/cicd/spider-release-register.py")
def get_spider_release_register_script():
    return PlainTextResponse(_read_cicd_file("spider_release_register.py"), media_type="text/x-python; charset=utf-8")


@router.get("/cicd/spider-project-init.sh")
def get_spider_project_init_script():
    return PlainTextResponse(_read_cicd_file("spider_project_init.sh"), media_type="text/x-shellscript; charset=utf-8")


@router.get("/cicd/templates/github-actions-spider-release.yml")
def get_github_actions_spider_release_template():
    return PlainTextResponse(_read_cicd_file("github-actions-spider-release.yml"), media_type="text/yaml; charset=utf-8")


@router.get("/cicd/templates/gitlab-ci-spider-release.yml")
def get_gitlab_ci_spider_release_template():
    return PlainTextResponse(_read_cicd_file("gitlab-ci-spider-release.yml"), media_type="text/yaml; charset=utf-8")


@router.get("/cicd/spider-projects/one-click-guide")
def get_spider_project_one_click_guide(provider: str = Query(default="github", pattern="^(github|gitlab)$"), company_id: int | None = Query(default=None, alias="companyId"), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(CicdGuideService(db).spider_project_one_click_guide(user, provider=provider, company_id=company_id))
