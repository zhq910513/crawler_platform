from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard-summaries", tags=["运行总览"])


@router.get("")
def get_dashboard_summary(user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(DashboardService(db).summary(user))
