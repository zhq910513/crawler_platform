from __future__ import annotations

from fastapi import status
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import CrawlerCompany, CrawlerCompanyDiscoveryToken, SysUser
from app.repositories.platform import CompanyRepository
from app.schemas import CompanyCreate, CompanyUpdate
from app.services.permissions import is_super_admin, require_super_admin, scoped_company_id
from app.services.audit import write_operation_log


import secrets
from app.utils import sha256_text


class CompanyService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = CompanyRepository(db)

    def list_companies(self, user: SysUser) -> list[CrawlerCompany]:
        if is_super_admin(user):
            return self.repo.list_companies()
        if not user.company_id:
            return []
        company = self.repo.get(user.company_id)
        return [company] if company else []

    def create_company(self, user: SysUser, payload: CompanyCreate) -> CrawlerCompany:
        require_super_admin(user)
        if self.repo.by_code(payload.company_code):
            raise AppError("公司编码已存在", code=40011)
        company = CrawlerCompany(
            company_code=payload.company_code,
            company_name=payload.company_name,
            timezone=payload.timezone,
            description=payload.description,
            created_by=user.user_id,
        )
        self.repo.add(company)
        self.db.flush()
        write_operation_log(self.db, user, None, operation_type="CREATE_COMPANY", resource_type="company", resource_id=str(company.company_id), after_data={"companyId": company.company_id, "companyCode": company.company_code, "companyName": company.company_name})
        self.db.commit()
        return company

    def update_company(self, user: SysUser, company_id: int, payload: CompanyUpdate) -> CrawlerCompany:
        require_super_admin(user)
        company = self.repo.get(company_id)
        if not company:
            raise AppError("资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        before = {c.name: getattr(company, c.name) for c in company.__table__.columns}
        updates = payload.model_dump(exclude_unset=True)
        for key, value in updates.items():
            setattr(company, key, value)
        after = {c.name: getattr(company, c.name) for c in company.__table__.columns}
        write_operation_log(self.db, user, None, operation_type="UPDATE_COMPANY", resource_type="company", resource_id=str(company.company_id), before_data=before, after_data=after)
        self.db.commit()
        return company

    def create_discovery_token(self, user: SysUser, company_id: int) -> dict:
        require_super_admin(user)
        company = self.repo.get(company_id)
        if not company:
            raise AppError("公司不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        raw = secrets.token_urlsafe(36)
        token = CrawlerCompanyDiscoveryToken(company_id=company_id, token_name="默认项目接入凭证", token_hash=sha256_text(raw), status="ENABLED")
        self.db.add(token)
        self.db.flush()
        write_operation_log(self.db, user, None, operation_type="CREATE_DISCOVERY_TOKEN", resource_type="company", resource_id=str(company_id), after_data={"tokenId": token.token_id, "companyId": company_id})
        self.db.commit()
        return {"tokenId": token.token_id, "discoveryToken": raw}
