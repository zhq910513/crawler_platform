from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.schemas import CronPreviewRequest
from app.services.cron_service import CronService
from app.services.permissions import is_super_admin

router = APIRouter(tags=["Cron 预览"])


@router.post("/cron-previews")
def create_cron_preview(payload: CronPreviewRequest, user: SysUser = Depends(get_current_user)):
    return ok(CronService.preview(payload.cron_expression, payload.timezone, payload.count, is_super_admin=is_super_admin(user)))
