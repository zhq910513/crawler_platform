from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import CrawlerCompany, CrawlerCompanyMember, SysUser
from app.schemas import CompanyCreate, CompanyMemberUpsert
from app.services.audit import write_operation_log
from app.services.permissions import company_role, is_super_admin, require_company_role

router = APIRouter(prefix="/companies", tags=["公司"])


def company_dict(db: Session, row: CrawlerCompany, user: SysUser) -> dict:
    return {
        "company_id": row.company_id,
        "company_code": row.company_code,
        "company_name": row.company_name,
        "status": row.status,
        "description": row.description,
        "role": company_role(db, user, row.company_id),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("")
def list_companies(db: Session = Depends(get_db), user: SysUser = Depends(get_current_user)) -> list[dict]:
    stmt = select(CrawlerCompany).order_by(CrawlerCompany.company_id.desc())
    if not is_super_admin(user):
        ids = select(CrawlerCompanyMember.company_id).where(CrawlerCompanyMember.user_id == user.user_id)
        stmt = stmt.where(CrawlerCompany.company_id.in_(ids))
    return [company_dict(db, row, user) for row in db.scalars(stmt).all()]


@router.post("")
def create_company(
    payload: CompanyCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="仅超级管理员可创建公司")
    if db.scalar(select(CrawlerCompany).where(CrawlerCompany.company_code == payload.company_code)):
        raise HTTPException(status_code=409, detail="公司编码已存在")
    row = CrawlerCompany(**payload.model_dump(), created_by=user.user_id)
    db.add(row)
    db.flush()
    db.add(CrawlerCompanyMember(company_id=row.company_id, user_id=user.user_id, role="OWNER"))
    write_operation_log(db, request, user, "CREATE", "COMPANY", row.company_id, after_data=payload.model_dump())
    db.commit()
    return company_dict(db, row, user)


@router.get("/{company_id}/members")
def list_members(company_id: int, db: Session = Depends(get_db), user: SysUser = Depends(get_current_user)) -> list[dict]:
    require_company_role(db, user, company_id, "MEMBER")
    rows = db.execute(
        select(CrawlerCompanyMember, SysUser)
        .join(SysUser, SysUser.user_id == CrawlerCompanyMember.user_id)
        .where(CrawlerCompanyMember.company_id == company_id)
        .order_by(CrawlerCompanyMember.member_id)
    ).all()
    return [{"user_id": account.user_id, "user_name": account.user_name, "nick_name": account.nick_name, "role": member.role} for member, account in rows]


@router.get("/{company_id}/user-options")
def user_options(company_id: int, db: Session = Depends(get_db), user: SysUser = Depends(get_current_user)) -> list[dict]:
    require_company_role(db, user, company_id, "MEMBER")
    rows = db.execute(
        select(SysUser)
        .join(CrawlerCompanyMember, CrawlerCompanyMember.user_id == SysUser.user_id)
        .where(CrawlerCompanyMember.company_id == company_id, SysUser.status.is_(True))
        .order_by(SysUser.user_name)
    ).scalars().all()
    return [{"user_id": x.user_id, "user_name": x.user_name, "nick_name": x.nick_name} for x in rows]


@router.put("/{company_id}/members")
def upsert_member(
    company_id: int,
    payload: CompanyMemberUpsert,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    require_company_role(db, user, company_id, "ADMIN")
    account = db.get(SysUser, payload.user_id)
    if not account:
        raise HTTPException(status_code=404, detail="用户不存在")
    row = db.scalar(select(CrawlerCompanyMember).where(
        CrawlerCompanyMember.company_id == company_id,
        CrawlerCompanyMember.user_id == payload.user_id,
    ))
    if row:
        row.role = payload.role
    else:
        row = CrawlerCompanyMember(company_id=company_id, user_id=payload.user_id, role=payload.role)
        db.add(row)
    write_operation_log(db, request, user, "UPSERT_MEMBER", "COMPANY", company_id, after_data=payload.model_dump())
    db.commit()
    return {"ok": True}


@router.delete("/{company_id}/members/{user_id}")
def delete_member(
    company_id: int,
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    require_company_role(db, user, company_id, "ADMIN")
    row = db.scalar(select(CrawlerCompanyMember).where(
        CrawlerCompanyMember.company_id == company_id,
        CrawlerCompanyMember.user_id == user_id,
    ))
    if not row:
        raise HTTPException(status_code=404, detail="公司成员不存在")
    if row.role == "OWNER":
        owners = db.scalar(select(func.count()).select_from(CrawlerCompanyMember).where(
            CrawlerCompanyMember.company_id == company_id,
            CrawlerCompanyMember.role == "OWNER",
        )) or 0
        if owners <= 1:
            raise HTTPException(status_code=409, detail="公司至少保留一名 OWNER")
    db.delete(row)
    write_operation_log(db, request, user, "DELETE_MEMBER", "COMPANY", company_id, before_data={"user_id": user_id})
    db.commit()
    return {"ok": True}
