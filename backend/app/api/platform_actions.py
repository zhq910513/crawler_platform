from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.services.platform_action_service import PlatformActionService

router = APIRouter(prefix="/platform-actions", tags=["平台动作"])


@router.get("")
def get_platform_action_status(user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(PlatformActionService(db).get_status(user))


@router.post("/agent-image-preparations")
def prepare_agent_image(user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(PlatformActionService(db).prepare_agent_image(user))
