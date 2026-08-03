from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError
from app.models import SysLoginLog, SysUser, SysUserSession
from app.repositories.users import SessionRepository, UserRepository
from app.schemas import LoginRequest
from app.security import create_access_token, create_force_login_token, decode_force_login_token, verify_password
from app.utils import utcnow
from app.services.audit import write_operation_log


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "")


def device_name(user_agent: str) -> str:
    ua = user_agent.lower()
    os_name = "未知系统"
    if "windows" in ua:
        os_name = "Windows"
    elif "mac os" in ua:
        os_name = "macOS"
    elif "linux" in ua:
        os_name = "Linux"
    browser = "浏览器"
    if "chrome" in ua:
        browser = "Chrome"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "safari" in ua:
        browser = "Safari"
    return f"{os_name} / {browser}"


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.sessions = SessionRepository(db)

    def create_session(self, payload: LoginRequest, request: Request) -> dict:
        user = self.users.by_user_name_for_update(payload.user_name)
        ip = client_ip(request)
        user_agent = request.headers.get("user-agent", "")[:500]
        if not user or user.status != "ENABLED" or not verify_password(payload.password, user.password_hash):
            self.db.add(SysLoginLog(user_id=user.user_id if user else None, user_name=payload.user_name, ip_address=ip, user_agent=user_agent, status="FAILED", message="用户名、密码错误或账户已停用"))
            self.db.commit()
            raise AppError("用户名、密码错误或账户已停用", code=40130, http_status=status.HTTP_401_UNAUTHORIZED)
        active = self.sessions.active_for_user(user.user_id)
        if active and active.last_active_at >= utcnow() - timedelta(minutes=settings.session_active_minutes):
            if not payload.force_login_token:
                token = create_force_login_token(user.user_id, active.session_id)
                raise AppError(
                    "该账号当前正在使用中",
                    code=40901,
                    http_status=status.HTTP_400_BAD_REQUEST,
                    data={"lastActiveAt": active.last_active_at, "deviceName": active.device_name, "loginIp": active.login_ip, "forceLoginToken": token},
                )
            try:
                forced = decode_force_login_token(payload.force_login_token)
            except Exception as exc:
                raise AppError("强制登录确认已失效，请重新登录", code=40902, http_status=status.HTTP_400_BAD_REQUEST) from exc
            if int(forced["sub"]) != user.user_id or forced["sid"] != active.session_id:
                raise AppError("强制登录确认不匹配，请重新登录", code=40903, http_status=status.HTTP_400_BAD_REQUEST)
        if active:
            active.session_status = "REPLACED"
            active.revoked_at = utcnow()
            active.revoke_reason = "您的账号已在其他设备登录，当前会话已被强制退出。"
        self.sessions.replace_active_sessions(user.user_id, "您的账号已在其他设备登录，当前会话已被强制退出。")
        session_id = uuid.uuid4().hex
        session = SysUserSession(
            session_id=session_id,
            user_id=user.user_id,
            company_id=user.company_id,
            session_status="ACTIVE",
            login_time=utcnow(),
            last_active_at=utcnow(),
            login_ip=ip,
            user_agent=user_agent,
            device_name=device_name(user_agent),
        )
        self.db.add(session)
        user.last_login_ip = ip
        user.last_login_at = utcnow()
        user.current_session_id = session_id
        self.db.add(SysLoginLog(user_id=user.user_id, user_name=user.user_name, ip_address=ip, user_agent=user_agent, status="SUCCESS", message="登录成功"))
        self.db.commit()
        token = create_access_token(user.user_id, session_id, user.role_type, user.company_id)
        return {"accessToken": token, "tokenType": "bearer", "sessionId": session_id, "passwordChangeRequired": bool(user.must_change_password), "user": self.user_payload(user)}

    def current_profile(self, user: SysUser, session: SysUserSession) -> dict:
        return {"session": session, "user": self.user_payload(user)}

    def touch_session(self, session: SysUserSession) -> SysUserSession:
        if session.last_active_at < utcnow() - timedelta(seconds=60):
            session.last_active_at = utcnow()
            self.db.commit()
        return session

    def logout(self, session: SysUserSession) -> None:
        session.session_status = "LOGGED_OUT"
        session.logout_time = utcnow()
        user = self.db.get(SysUser, session.user_id)
        if user and user.current_session_id == session.session_id:
            user.current_session_id = ""
        self.db.commit()


    def revoke_user_session(self, current_user: SysUser, target_user_id: int, reason: str = "管理员强制下线") -> dict:
        from app.services.permissions import require_super_admin
        require_super_admin(current_user)
        sessions = list(self.db.query(SysUserSession).filter(SysUserSession.user_id == target_user_id, SysUserSession.session_status == "ACTIVE").all())
        now = utcnow()
        for session in sessions:
            session.session_status = "ADMIN_REVOKED"
            session.revoked_at = now
            session.revoke_reason = reason or "您的账号已被管理员强制下线。"
        target_user = self.db.get(SysUser, target_user_id)
        if target_user:
            target_user.current_session_id = ""
        write_operation_log(self.db, current_user, None, operation_type="REVOKE_USER_SESSION", resource_type="user", resource_id=str(target_user_id), after_data={"revokedCount": len(sessions), "reason": reason})
        self.db.commit()
        return {"revokedCount": len(sessions)}

    @staticmethod
    def user_payload(user: SysUser) -> dict:
        return {
            "userId": user.user_id,
            "companyId": user.company_id,
            "userName": user.user_name,
            "nickName": user.nick_name,
            "roleType": user.role_type,
            "status": user.status,
            "isSuperAdmin": user.role_type == "SUPER_ADMIN",
            "passwordChangeRequired": bool(user.must_change_password),
            "passwordUpdatedAt": user.password_updated_at,
        }
