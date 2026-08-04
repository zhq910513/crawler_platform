from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.schemas import TaskSchedulePanelQuery
from app.services.task_schedule_panel_service import TaskSchedulePanelService

router = APIRouter(prefix="/task-schedule-panels", tags=["任务调度面板"])


@router.get("")
def list_task_schedule_panels(
    query: Annotated[TaskSchedulePanelQuery, Depends()],
    user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ok(TaskSchedulePanelService(db).list_panels(user, query))
