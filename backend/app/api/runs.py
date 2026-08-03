from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.schemas import ManualRunCreate, RunLogTailQuery
from app.services.run_service import RunService
from app.services.run_log_service import RunLogService

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

@router.get("/{run_id}/events")
def list_run_events(run_id: int, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(RunLogService(db).list_events(user, run_id))


@router.get("/{run_id}/log-tails")
def get_run_log_tail(run_id: int, after_seq: int = Query(default=0, ge=0), limit: int = Query(default=200, ge=1, le=1000), keyword: str = Query(default="", max_length=200), stream: str = Query(default="", max_length=20), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(RunLogService(db).tail_logs(user, run_id, RunLogTailQuery(afterSeq=after_seq, limit=limit, keyword=keyword, stream=stream)))


@router.get("/{run_id}/log-downloads")
def get_run_log_download(run_id: int, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(RunLogService(db).download_logs(user, run_id))


@router.get("/{run_id}/diagnoses")
def get_run_diagnosis(run_id: int, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(RunLogService(db).diagnosis(user, run_id))
