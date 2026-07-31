from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.schemas import ScheduleUpdate, TaskFromDefinitionCreate, TaskUpdate
from app.services.task_service import TaskService

router = APIRouter(tags=["任务"])


@router.get("/projects/{project_id}/task-definitions")
def list_task_definitions(project_id: int, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(TaskService(db).list_definitions(user, project_id))


@router.get("/tasks")
def list_tasks(company_id: int | None = Query(default=None), project_id: int | None = Query(default=None), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(TaskService(db).list_tasks(user, company_id, project_id))


@router.post("/tasks")
def create_task(payload: TaskFromDefinitionCreate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(TaskService(db).create_from_definition(user, payload))


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, payload: TaskUpdate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(TaskService(db).update_task(user, task_id, payload))


@router.patch("/tasks/{task_id}/schedules")
def update_task_schedule(task_id: int, payload: ScheduleUpdate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(TaskService(db).update_schedule(user, task_id, payload))
