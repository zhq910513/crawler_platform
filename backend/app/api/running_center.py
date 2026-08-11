from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.services.running_center_service import RunningCenterService

router = APIRouter(prefix="/running-center", tags=["运行中心"])


@router.get("")
def get_running_center(company_id: int | None = Query(default=None), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(RunningCenterService(db).summary(user, company_id))
