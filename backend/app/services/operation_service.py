from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SysOperationLog, SysUser
from app.services.permissions import require_super_admin


class OperationService:
    def __init__(self, db: Session):
        self.db = db

    def list_logs(self, user: SysUser) -> list[SysOperationLog]:
        require_super_admin(user)
        return list(self.db.scalars(select(SysOperationLog).order_by(SysOperationLog.created_at.desc()).limit(500)).all())
