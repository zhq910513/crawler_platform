from __future__ import annotations

import re
from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import SysUser, SysUserSession
from app.schemas import OwnPasswordUpdate, UserPasswordResetCreate
from app.security import hash_password, verify_password
from app.services.audit import write_operation_log
from app.services.permissions import require_super_admin
from app.utils import utcnow

_PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,200}$")


def validate_password_strength(password: str) -> None:
    if not _PASSWORD_RE.match(password or ""):
        raise AppError("新密码至少 8 位，必须包含大小写字母、数字和特殊字符", code=40024, http_status=status.HTTP_400_BAD_REQUEST)


class PasswordService:
    def __init__(self, db: Session):
        self.db = db

    def change_own_password(self, current_user: SysUser, payload: OwnPasswordUpdate) -> dict:
        if payload.new_password != payload.confirm_password:
            raise AppError("两次输入的新密码不一致", code=40025, http_status=status.HTTP_400_BAD_REQUEST)
        if not verify_password(payload.old_password, current_user.password_hash):
            raise AppError("旧密码错误", code=40026, http_status=status.HTTP_400_BAD_REQUEST)
        if verify_password(payload.new_password, current_user.password_hash):
            raise AppError("新密码不能与旧密码相同", code=40027, http_status=status.HTTP_400_BAD_REQUEST)
        validate_password_strength(payload.new_password)
        current_user.password_hash = hash_password(payload.new_password)
        current_user.password_updated_at = utcnow()
        current_user.must_change_password = False
        revoked_count = self._revoke_sessions(current_user.user_id, "PASSWORD_CHANGED", "密码已修改，请重新登录。")
        current_user.current_session_id = ""
        write_operation_log(
            self.db,
            current_user,
            None,
            operation_type="CHANGE_OWN_PASSWORD",
            resource_type="user",
            resource_id=str(current_user.user_id),
            after_data={"userId": current_user.user_id, "revokedCount": revoked_count},
        )
        self.db.commit()
        return {"revokedCount": revoked_count, "reloginRequired": True}

    def reset_user_password(self, current_user: SysUser, target_user_id: int, payload: UserPasswordResetCreate) -> dict:
        require_super_admin(current_user)
        target = self.db.get(SysUser, target_user_id)
        if not target:
            raise AppError("用户不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        validate_password_strength(payload.new_password)
        target.password_hash = hash_password(payload.new_password)
        target.password_updated_at = utcnow()
        target.must_change_password = payload.must_change_password
        revoked_count = self._revoke_sessions(target.user_id, "PASSWORD_RESET", "管理员已重置密码，请重新登录。")
        target.current_session_id = ""
        write_operation_log(
            self.db,
            current_user,
            None,
            operation_type="RESET_USER_PASSWORD",
            resource_type="user",
            resource_id=str(target.user_id),
            after_data={"targetUserId": target.user_id, "mustChangePassword": target.must_change_password, "revokedCount": revoked_count},
        )
        self.db.commit()
        return {"userId": target.user_id, "revokedCount": revoked_count, "mustChangePassword": target.must_change_password}

    def _revoke_sessions(self, user_id: int, status_value: str, reason: str) -> int:
        sessions = list(self.db.scalars(select(SysUserSession).where(SysUserSession.user_id == user_id, SysUserSession.session_status == "ACTIVE")).all())
        now = utcnow()
        for session in sessions:
            session.session_status = status_value
            session.revoked_at = now
            session.revoke_reason = reason
        return len(sessions)
