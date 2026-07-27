from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import CrawlerAgent, SysUser
from app.security import decode_access_token
from app.utils import sha256_text


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> SysUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已失效")
    token = authorization[7:].strip()
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效登录凭证") from exc
    user = db.get(SysUser, user_id)
    if not user or not user.status:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账户不存在或已停用")
    request.state.current_user = user
    return user


def require_admin(user: SysUser = Depends(get_current_user)) -> SysUser:
    if user.role_type != "SUPER_ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅超级管理员可执行此操作")
    return user


def get_agent(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> CrawlerAgent:
    if not authorization or not authorization.startswith("Agent "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Agent 认证失败")
    token_hash = sha256_text(authorization[6:].strip())
    agent = db.scalar(select(CrawlerAgent).where(CrawlerAgent.token_hash == token_hash))
    if not agent:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Agent Token 无效")
    return agent


def verify_cicd_token(x_cicd_token: str | None = Header(default=None)) -> None:
    if not x_cicd_token or x_cicd_token != settings.cicd_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="CI/CD Token 无效")
