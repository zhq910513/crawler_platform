from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import SysOperationLog, SysUser


def _json_safe(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def write_operation_log(
    db: Session,
    request: Request,
    user: SysUser | None,
    operation_type: str,
    resource_type: str,
    resource_id: str | int = "",
    before_data: dict[str, Any] | None = None,
    after_data: dict[str, Any] | None = None,
    status: str = "SUCCESS",
    error_message: str = "",
) -> None:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    ip_address = forwarded or (request.client.host if request.client else "")
    db.add(
        SysOperationLog(
            user_id=user.user_id if user else None,
            user_name=user.user_name if user else "",
            operation_type=operation_type,
            resource_type=resource_type,
            resource_id=str(resource_id),
            request_method=request.method,
            request_path=request.url.path,
            before_data=_json_safe(before_data),
            after_data=_json_safe(after_data),
            ip_address=ip_address,
            status=status,
            error_message=error_message,
        )
    )
