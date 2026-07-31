from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.schemas import ManualRunCreate
from app.services.run_service import RunService

router = APIRouter(prefix="/runs", tags=["执行"])


@router.get("")
def list_runs(company_id: int | None = Query(default=None), project_id: int | None = Query(default=None), task_id: int | None = Query(default=None), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(RunService(db).list_runs(user, company_id, project_id, task_id))


@router.post("")
def create_run(payload: ManualRunCreate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(RunService(db).create_manual_run(user, payload))


@router.post("/{run_id}/cancellation-requests")
def create_cancellation_request(run_id: int, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(RunService(db).request_cancel(user, run_id))
