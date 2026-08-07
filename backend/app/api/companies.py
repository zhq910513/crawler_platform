from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.schemas import CompanyCreate, CompanyUpdate
from app.services.company_service import CompanyService

router = APIRouter(prefix="/companies", tags=["公司"])


@router.get("")
def list_companies(user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(CompanyService(db).list_companies(user))


@router.post("")
def create_company(payload: CompanyCreate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(CompanyService(db).create_company(user, payload))


@router.patch("/{company_id}")
def update_company(company_id: int, payload: CompanyUpdate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(CompanyService(db).update_company(user, company_id, payload))


@router.post("/{company_id}/discovery-tokens")
def create_discovery_token(company_id: int, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(CompanyService(db).create_discovery_token(user, company_id))


@router.get("/{company_id}/setup-status")
def get_company_setup_status(company_id: int, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.company_setup_service import CompanySetupService
    return ok(CompanySetupService(db).get_setup_status(user, company_id))
