from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.schemas import CompanyResourceConfigCreate, CompanyResourceConfigTest
from app.services.company_resource_service import CompanyResourceService

router = APIRouter(prefix="/company-resource-configs", tags=["公司资源配置"])


@router.get("")
def list_resource_configs(company_id: int | None = Query(default=None), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(CompanyResourceService(db).list_resources(user, company_id))


@router.post("")
def upsert_resource_config(payload: CompanyResourceConfigCreate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(CompanyResourceService(db).upsert_resource(user, payload))


@router.post("/{config_id}/tests")
def test_resource_config(config_id: int, payload: CompanyResourceConfigTest, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(CompanyResourceService(db).test_resource(user, config_id, payload))
