from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import SysOperationLog, SysUser
from app.utils import api_data


def write_operation_log(db: Session, user: SysUser | None, request: Request | None, operation_type: str, resource_type: str, resource_id: str = "", before_data: dict[str, Any] | None = None, after_data: dict[str, Any] | None = None, status: str = "SUCCESS", error_message: str = "") -> None:
    ip = ""
    method = ""
    path = ""
    if request:
        ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
        method = request.method
        path = request.url.path
    db.add(
        SysOperationLog(
            user_id=user.user_id if user else None,
            user_name=user.user_name if user else "",
            operation_type=operation_type,
            resource_type=resource_type,
            resource_id=resource_id,
            request_method=method,
            request_path=path,
            before_data=api_data(before_data) if before_data is not None else None,
            after_data=api_data(after_data) if after_data is not None else None,
            ip_address=ip,
            status=status,
            error_message=error_message,
        )
    )
