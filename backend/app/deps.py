from __future__ import annotations

from datetime import timedelta

from fastapi import Depends, Header, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.errors import AppError
from app.models import CrawlerAgent, SysUser, SysUserSession
from app.security import decode_access_token
from app.services.permissions import require_super_admin
from app.utils import sha256_text, utcnow


def _relative_api_path(request: Request) -> str:
    path = request.url.path
    if path.startswith(settings.api_prefix):
        return path.removeprefix(settings.api_prefix) or "/"
    return path


def _allows_forced_password_change_access(request: Request) -> bool:
    path = _relative_api_path(request)
    method = request.method.upper()
    if method == "PATCH" and path in {"/users/me/password", "/users/current/passwords"}:
        return True
    if path.startswith("/sessions/") and method in {"GET", "PATCH", "DELETE"}:
        return True
    return False


def get_current_user(request: Request, authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> SysUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError("未登录或登录已失效", code=40101, http_status=status.HTTP_401_UNAUTHORIZED)
    token = authorization[7:].strip()
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
        session_id = str(payload["sid"])
    except Exception as exc:
        raise AppError("无效登录凭证", code=40102, http_status=status.HTTP_401_UNAUTHORIZED) from exc
    user = db.get(SysUser, user_id)
    session = db.get(SysUserSession, session_id)
    if not user or user.status != "ENABLED":
        if session and session.session_status == "ACTIVE":
            session.session_status = "USER_DISABLED"
            session.revoked_at = utcnow()
            db.commit()
        raise AppError("账户不存在或已停用", code=40103, http_status=status.HTTP_401_UNAUTHORIZED)
    if not session or session.user_id != user.user_id or session.session_status != "ACTIVE" or user.current_session_id != session.session_id:
        reason = session.revoke_reason if session else "会话已失效"
        code = 40110 if session and session.session_status == "REPLACED" else 40104
        raise AppError(reason or "登录会话已失效", code=code, http_status=status.HTTP_401_UNAUTHORIZED)
    if user.must_change_password and not _allows_forced_password_change_access(request):
        raise AppError("当前账号必须先修改初始密码", code=40320, http_status=status.HTTP_403_FORBIDDEN, data={"passwordChangeRequired": True})
    if request.headers.get("x-user-active") == "1" and session.last_active_at < utcnow() - timedelta(seconds=60):
        session.last_active_at = utcnow()
        db.commit()
    request.state.current_user = user
    request.state.current_session = session
    return user


def get_current_session(request: Request, user: SysUser = Depends(get_current_user)) -> SysUserSession:
    return request.state.current_session


def require_admin(user: SysUser = Depends(get_current_user)) -> SysUser:
    require_super_admin(user)
    return user


def get_agent(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> CrawlerAgent:
    if not authorization or not authorization.startswith("Agent "):
        raise AppError("Agent 认证失败", code=40120, http_status=status.HTTP_401_UNAUTHORIZED)
    token_hash = sha256_text(authorization[6:].strip())
    from app.repositories.platform import AgentRepository

    agent = AgentRepository(db).by_token_hash(token_hash)
    if not agent:
        raise AppError("Agent Token 无效", code=40121, http_status=status.HTTP_401_UNAUTHORIZED)
    return agent


def is_session_online(session: SysUserSession) -> bool:
    return session.session_status == "ACTIVE" and session.last_active_at >= utcnow() - timedelta(minutes=settings.session_active_minutes)
