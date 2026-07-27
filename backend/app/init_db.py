from __future__ import annotations

from sqlalchemy import select

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import SysUser
from app.security import hash_password


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        admin = db.scalar(select(SysUser).where(SysUser.user_name == settings.admin_username))
        if not admin:
            db.add(
                SysUser(
                    user_name=settings.admin_username,
                    nick_name=settings.admin_nickname,
                    password_hash=hash_password(settings.admin_password),
                    role_type="SUPER_ADMIN",
                    status=True,
                )
            )
            db.commit()
            print(f"Created default admin user: {settings.admin_username}")


if __name__ == "__main__":
    init_db()
