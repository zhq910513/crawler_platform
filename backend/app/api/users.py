from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.models import SysUser
from app.schemas import UserCreate, UserInfo, UserUpdate
from app.security import hash_password
from app.services.audit import write_operation_log

router = APIRouter(prefix="/users", tags=["用户"])


@router.get("")
def list_users(db: Session = Depends(get_db), _: SysUser = Depends(require_admin)) -> list[dict]:
    rows = db.scalars(select(SysUser).order_by(SysUser.user_id.asc())).all()
    return [UserInfo.model_validate(row).model_dump() for row in rows]


@router.post("")
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(require_admin),
) -> dict:
    if db.scalar(select(SysUser).where(SysUser.user_name == payload.user_name)):
        raise HTTPException(status_code=409, detail="用户名已存在")
    row = SysUser(
        user_name=payload.user_name,
        nick_name=payload.nick_name,
        password_hash=hash_password(payload.password),
        role_type=payload.role_type,
        status=payload.status,
    )
    db.add(row)
    db.flush()
    write_operation_log(db, request, user, "CREATE", "USER", row.user_id, after_data={"user_name": row.user_name, "role_type": row.role_type})
    db.commit()
    return UserInfo.model_validate(row).model_dump()


@router.put("/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(require_admin),
) -> dict:
    row = db.get(SysUser, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    before = {"nick_name": row.nick_name, "role_type": row.role_type, "status": row.status}
    for field in ("nick_name", "role_type", "status"):
        value = getattr(payload, field)
        if value is not None:
            setattr(row, field, value)
    if payload.password:
        row.password_hash = hash_password(payload.password)
    after = {"nick_name": row.nick_name, "role_type": row.role_type, "status": row.status}
    write_operation_log(db, request, user, "UPDATE", "USER", row.user_id, before, after)
    db.commit()
    return UserInfo.model_validate(row).model_dump()
