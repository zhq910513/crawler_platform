from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.services.operation_service import OperationService

router = APIRouter(prefix="/operation-logs", tags=["操作日志"])


@router.get("")
def list_operation_logs(user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(OperationService(db).list_logs(user))
