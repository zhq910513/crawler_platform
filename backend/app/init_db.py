
from sqlalchemy import select, text

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import SysUser
from app.security import hash_password


_INIT_LOCK_NAME = "crawler_platform:init_db"


def _create_schema_and_admin() -> None:
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


def init_db() -> None:
    if not settings.database_url.startswith("mysql"):
        _create_schema_and_admin()
        return

    with engine.connect() as lock_conn:
        acquired = lock_conn.scalar(
            text("SELECT GET_LOCK(:name, :timeout)"),
            {"name": _INIT_LOCK_NAME, "timeout": 120},
        )
        if acquired != 1:
            raise RuntimeError("Unable to acquire database initialization lock")

        try:
            _create_schema_and_admin()
        finally:
            lock_conn.execute(
                text("SELECT RELEASE_LOCK(:name)"),
                {"name": _INIT_LOCK_NAME},
            )
            lock_conn.commit()


if __name__ == "__main__":
    init_db()
