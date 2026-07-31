from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.services.release_service import ReleaseService

router = APIRouter(prefix="/releases", tags=["发布版本"])


@router.get("")
def list_releases(company_id: int | None = Query(default=None), project_id: int | None = Query(default=None), user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ReleaseService(db).list_releases(user, company_id, project_id))
