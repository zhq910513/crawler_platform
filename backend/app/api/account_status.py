from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_agent, get_current_user
from app.models import CrawlerAgent, SysUser
from app.responses import ok
from app.schemas import AccountCredentialEnableUpdate, AccountStatusEventCreate, CredentialLeaseAcquire, CredentialLeaseRelease, CredentialSubjectBindingCreate, CredentialSubjectBindingUpdate
from app.services.account_status_service import AccountStatusService

router = APIRouter(tags=["账号状态"])


@router.get("/account-credentials")
def list_account_credentials(company_id: int | None = Query(default=None), platform_code: str = Query(default="", max_length=100), credential_key: str = Query(default="", max_length=150), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AccountStatusService(db).list_credentials(user, company_id=company_id, platform_code=platform_code, credential_key=credential_key))


@router.get("/account-credentials/{credential_id}/status-events")
def list_account_status_events(credential_id: int, limit: int = Query(default=100, ge=1, le=500), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AccountStatusService(db).list_events(user, credential_id, limit=limit))


@router.get("/credential-subject-bindings")
def list_credential_subject_bindings(company_id: int | None = Query(default=None), platform_code: str = Query(default="", max_length=100), subject_type: str = Query(default="", max_length=80), credential_key: str = Query(default="", max_length=150), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AccountStatusService(db).list_subject_bindings(user, company_id=company_id, platform_code=platform_code, subject_type=subject_type, credential_key=credential_key))


@router.post("/credential-subject-bindings")
def create_credential_subject_binding(payload: CredentialSubjectBindingCreate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AccountStatusService(db).create_subject_binding(user, payload))


@router.patch("/credential-subject-bindings/{binding_id}")
def update_credential_subject_binding(binding_id: int, payload: CredentialSubjectBindingUpdate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AccountStatusService(db).update_subject_binding(user, binding_id, payload))


@router.patch("/account-credentials/{credential_id}/enabled")
def set_account_credential_enabled(credential_id: int, payload: AccountCredentialEnableUpdate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AccountStatusService(db).set_enabled(user, credential_id, payload.enabled))




@router.get("/credential-leases")
def list_credential_leases(company_id: int | None = Query(default=None), platform_code: str = Query(default="", max_length=100), credential_key: str = Query(default="", max_length=150), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AccountStatusService(db).list_leases(user, company_id=company_id, platform_code=platform_code, credential_key=credential_key))


@router.post("/credential-leases/acquire")
def acquire_credential_lease(payload: CredentialLeaseAcquire, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AccountStatusService(db).acquire_lease(user, payload))


@router.post("/credential-leases/release")
def release_credential_lease(payload: CredentialLeaseRelease, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AccountStatusService(db).release_lease(user, payload))


@router.post("/agent-credential-leases/acquire")
def agent_acquire_credential_lease(payload: CredentialLeaseAcquire, agent: CrawlerAgent = Depends(get_agent), db: Session = Depends(get_db)):
    return ok(AccountStatusService(db).acquire_lease(None, payload, agent=agent))


@router.post("/agent-credential-leases/release")
def agent_release_credential_lease(payload: CredentialLeaseRelease, agent: CrawlerAgent = Depends(get_agent), db: Session = Depends(get_db)):
    return ok(AccountStatusService(db).release_lease(None, payload, agent=agent))


@router.post("/account-status-events")
def create_account_status_event(payload: AccountStatusEventCreate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AccountStatusService(db).ingest_user_event(user, payload))


@router.post("/agent-account-status-events")
def create_agent_account_status_event(payload: AccountStatusEventCreate, agent: CrawlerAgent = Depends(get_agent), db: Session = Depends(get_db)):
    return ok(AccountStatusService(db).ingest_agent_event(agent, payload))
