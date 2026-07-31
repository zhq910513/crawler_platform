from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import SysUser
from app.security import hash_password


def init_schema() -> None:
    raise RuntimeError("生产和测试环境必须通过 Alembic migration_main 执行迁移，禁止 ORM 自动建表初始化数据库")


def init_admin(db: Session) -> None:
    exists = db.scalar(select(SysUser).where(SysUser.user_name == settings.admin_username))
    if exists:
        return
    admin = SysUser(
        user_name=settings.admin_username,
        nick_name=settings.admin_nickname,
        password_hash=hash_password(settings.admin_password),
        role_type="SUPER_ADMIN",
        status="ENABLED",
    )
    db.add(admin)
    db.commit()
