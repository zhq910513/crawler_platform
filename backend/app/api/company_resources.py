from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.schemas import CompanyResourceConfigCreate, CompanyResourceConfigTest, CompanyResourceStatusUpdate
from app.services.company_resource_service import CompanyResourceService

router = APIRouter(prefix="/company-resource-configs", tags=["公司数据资源配置"])


@router.get("")
def list_resource_configs(
    company_id: int | None = Query(default=None, alias="companyId"),
    project_id: int | None = Query(default=None, alias="projectId"),
    resource_category: str | None = Query(default=None, alias="resourceCategory"),
    resource_engine: str | None = Query(default=None, alias="resourceEngine"),
    resource_role: str | None = Query(default=None, alias="resourceRole"),
    enabled: bool | None = Query(default=None),
    test_status: str | None = Query(default=None, alias="testStatus"),
    keyword: str | None = Query(default=None),
    user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ok(
        CompanyResourceService(db).list_resources(
            user,
            company_id,
            project_id=project_id,
            resource_category=resource_category,
            resource_engine=resource_engine,
            resource_role=resource_role,
            enabled=enabled,
            test_status=test_status,
            keyword=keyword,
        )
    )


@router.post("")
def upsert_resource_config(payload: CompanyResourceConfigCreate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(CompanyResourceService(db).upsert_resource(user, payload))


@router.post("/{config_id}/tests")
def test_resource_config(config_id: int, payload: CompanyResourceConfigTest, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(CompanyResourceService(db).test_resource(user, config_id, payload))


@router.patch("/{config_id}/status")
def update_resource_status(config_id: int, payload: CompanyResourceStatusUpdate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(CompanyResourceService(db).update_status(user, config_id, payload))
