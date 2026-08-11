from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import AppError
from app.deps import get_current_session, get_current_user
from app.models import SysUser, SysUserSession
from app.responses import ok
from app.schemas import LoginRequest, SessionActivityUpdate
from app.services.auth_service import AuthService

router = APIRouter(prefix="/sessions", tags=["会话"])


def _require_current_session_path(session_id: str, session: SysUserSession) -> None:
    if session_id != session.session_id:
        raise AppError("只能操作当前登录会话", code=40321, http_status=status.HTTP_403_FORBIDDEN)


@router.post("")
def create_session(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    return ok(AuthService(db).create_session(payload, request))


@router.get("/{session_id}")
def get_session_profile(session_id: str, user: SysUser = Depends(get_current_user), session: SysUserSession = Depends(get_current_session), db: Session = Depends(get_db)):
    _require_current_session_path(session_id, session)
    return ok(AuthService(db).current_profile(user, session))


@router.patch("/{session_id}")
def update_session_activity(session_id: str, payload: SessionActivityUpdate, session: SysUserSession = Depends(get_current_session), db: Session = Depends(get_db)):
    _require_current_session_path(session_id, session)
    return ok(AuthService(db).touch_session(session))


@router.delete("/{session_id}")
def delete_session(session_id: str, session: SysUserSession = Depends(get_current_session), db: Session = Depends(get_db)):
    _require_current_session_path(session_id, session)
    AuthService(db).logout(session)
    return ok({"deleted": True})
