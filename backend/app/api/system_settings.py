from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.schemas import SystemSettingsUpdate
from app.services.system_config_service import SystemConfigService

router = APIRouter(prefix="/system-settings", tags=["系统设置"])


@router.get("")
def get_system_settings(user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(SystemConfigService(db).get_system_settings())


@router.patch("")
def update_system_settings(payload: SystemSettingsUpdate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(SystemConfigService(db).update_system_settings(user, payload))
