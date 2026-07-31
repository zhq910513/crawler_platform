from __future__ import annotations

from fastapi import status
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import SysUser
from app.repositories.platform import CompanyRepository
from app.repositories.users import UserRepository
from app.schemas import UserCreate, UserUpdate
from app.security import hash_password
from app.services.permissions import require_super_admin, scoped_company_id
from app.services.audit import write_operation_log


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.companies = CompanyRepository(db)

    def list_users(self, current_user: SysUser) -> list[SysUser]:
        require_super_admin(current_user)
        return self.users.list_users()

    def create_user(self, current_user: SysUser, payload: UserCreate) -> SysUser:
        require_super_admin(current_user)
        if self.users.by_user_name(payload.user_name):
            raise AppError("用户名已存在", code=40021)
        if payload.role_type == "NORMAL_USER" and not payload.company_id:
            raise AppError("普通用户必须绑定归属公司", code=40022)
        if payload.company_id and not self.companies.get(payload.company_id):
            raise AppError("公司不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        user = SysUser(
            company_id=payload.company_id,
            user_name=payload.user_name,
            nick_name=payload.nick_name,
            password_hash=hash_password(payload.password),
            role_type=payload.role_type,
            status=payload.status,
        )
        self.users.add(user)
        self.db.flush()
        write_operation_log(self.db, current_user, None, operation_type="CREATE_USER", resource_type="user", resource_id=str(user.user_id), after_data={"userId": user.user_id, "userName": user.user_name, "companyId": user.company_id, "roleType": user.role_type, "status": user.status})
        self.db.commit()
        return user

    def update_user(self, current_user: SysUser, user_id: int, payload: UserUpdate) -> SysUser:
        require_super_admin(current_user)
        user = self.users.get(user_id)
        if not user:
            raise AppError("资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        before = {"userId": user.user_id, "userName": user.user_name, "companyId": user.company_id, "nickName": user.nick_name, "roleType": user.role_type, "status": user.status}
        updates = payload.model_dump(exclude_unset=True)
        password_changed = bool(updates.get("password"))
        if "password" in updates and updates["password"]:
            user.password_hash = hash_password(updates.pop("password"))
        for key, value in updates.items():
            setattr(user, key, value)
        if user.role_type == "NORMAL_USER" and not user.company_id:
            raise AppError("普通用户必须绑定归属公司", code=40022)
        after = {"userId": user.user_id, "userName": user.user_name, "companyId": user.company_id, "nickName": user.nick_name, "roleType": user.role_type, "status": user.status, "passwordChanged": password_changed}
        write_operation_log(self.db, current_user, None, operation_type="UPDATE_USER", resource_type="user", resource_id=str(user.user_id), before_data=before, after_data=after)
        self.db.commit()
        return user
