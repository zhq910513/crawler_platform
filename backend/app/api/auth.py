from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SysLoginLog, SysUser
from app.schemas import LoginRequest, LoginResponse, UserInfo
from app.security import create_access_token, verify_password
from app.utils import utcnow

router = APIRouter(prefix="/auth", tags=["认证"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "")


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.scalar(select(SysUser).where(SysUser.user_name == payload.user_name))
    ip = _client_ip(request)
    user_agent = request.headers.get("user-agent", "")[:500]
    if not user or not user.status or not verify_password(payload.password, user.password_hash):
        db.add(
            SysLoginLog(
                user_id=user.user_id if user else None,
                user_name=payload.user_name,
                ip_address=ip,
                user_agent=user_agent,
                status="FAILED",
                message="用户名、密码错误或账户已停用",
            )
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名、密码错误或账户已停用")
    user.last_login_ip = ip
    user.last_login_at = utcnow()
    db.add(
        SysLoginLog(
            user_id=user.user_id,
            user_name=user.user_name,
            ip_address=ip,
            user_agent=user_agent,
            status="SUCCESS",
            message="登录成功",
        )
    )
    db.commit()
    token = create_access_token(str(user.user_id), {"role": user.role_type})
    return LoginResponse(access_token=token, user=UserInfo.model_validate(user))


@router.get("/me", response_model=UserInfo)
def me(user: SysUser = Depends(get_current_user)) -> UserInfo:
    return UserInfo.model_validate(user)
