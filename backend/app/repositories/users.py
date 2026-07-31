from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import SysUser, SysUserSession
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[SysUser]):
    def __init__(self, db: Session):
        super().__init__(db, SysUser)

    def by_user_name(self, user_name: str) -> SysUser | None:
        return self.db.scalar(select(SysUser).where(SysUser.user_name == user_name))

    def by_user_name_for_update(self, user_name: str) -> SysUser | None:
        return self.db.scalar(select(SysUser).where(SysUser.user_name == user_name).with_for_update())

    def list_users(self, company_id: int | None = None) -> list[SysUser]:
        stmt = select(SysUser).order_by(SysUser.created_at.desc())
        if company_id is not None:
            stmt = stmt.where(SysUser.company_id == company_id)
        return list(self.db.scalars(stmt).all())


class SessionRepository(BaseRepository[SysUserSession]):
    def __init__(self, db: Session):
        super().__init__(db, SysUserSession)

    def active_for_user(self, user_id: int) -> SysUserSession | None:
        return self.db.scalar(
            select(SysUserSession)
            .where(SysUserSession.user_id == user_id, SysUserSession.session_status == "ACTIVE")
            .order_by(SysUserSession.last_active_at.desc())
        )

    def replace_active_sessions(self, user_id: int, reason: str) -> None:
        self.db.execute(
            update(SysUserSession)
            .where(SysUserSession.user_id == user_id, SysUserSession.session_status == "ACTIVE")
            .values(session_status="REPLACED", revoked_at=__import__("app.utils", fromlist=["utcnow"]).utcnow(), revoke_reason=reason)
        )
