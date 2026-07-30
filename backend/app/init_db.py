from __future__ import annotations

from sqlalchemy import select

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import CrawlerCompany, CrawlerCompanyMember, SysUser
from app.security import hash_password


def init_db() -> None:
    # 生产环境由 Alembic 负责结构升级；create_all 仅补齐全新/测试数据库中不存在的表。
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        admin = db.scalar(select(SysUser).where(SysUser.user_name == settings.admin_username))
        if not admin:
            admin = SysUser(
                user_name=settings.admin_username,
                nick_name=settings.admin_nickname,
                password_hash=hash_password(settings.admin_password),
                role_type="SUPER_ADMIN",
                status=True,
            )
            db.add(admin)
            db.flush()
            print(f"Created default admin user: {settings.admin_username}", flush=True)
        company = db.scalar(select(CrawlerCompany).where(CrawlerCompany.company_code == "default"))
        if not company:
            company = CrawlerCompany(company_code="default", company_name="默认公司", description="升级兼容默认公司", created_by=admin.user_id)
            db.add(company)
            db.flush()
        member = db.scalar(select(CrawlerCompanyMember).where(
            CrawlerCompanyMember.company_id == company.company_id,
            CrawlerCompanyMember.user_id == admin.user_id,
        ))
        if not member:
            db.add(CrawlerCompanyMember(company_id=company.company_id, user_id=admin.user_id, role="OWNER"))
        db.commit()


if __name__ == "__main__":
    init_db()
