from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysUser
from app.responses import ok
from app.schemas import UserCreate, UserUpdate, UserSessionRevoke
from app.services.user_service import UserService
from app.services.auth_service import AuthService

router = APIRouter(prefix="/users", tags=["用户"])


@router.get("")
def list_users(user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(UserService(db).list_users(user))


@router.post("")
def create_user(payload: UserCreate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(UserService(db).create_user(user, payload))


@router.patch("/{user_id}")
def update_user(user_id: int, payload: UserUpdate, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(UserService(db).update_user(user, user_id, payload))


@router.post("/{user_id}/session-revocations")
def create_user_session_revocation(user_id: int, payload: UserSessionRevoke, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(AuthService(db).revoke_user_session(user, user_id, payload.reason))
